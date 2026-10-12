from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from redis import Redis
from redis.exceptions import RedisError

from core.errors import ApplicationError

_RATE_SCRIPT = """
for i, key in ipairs(KEYS) do
  if tonumber(redis.call('GET', key) or '0') >= tonumber(ARGV[(i-1)*2+1]) then
    return math.max(1, redis.call('TTL', key))
  end
end
for i, key in ipairs(KEYS) do
  if redis.call('INCR', key) == 1 then
    redis.call('EXPIRE', key, ARGV[(i-1)*2+2])
  end
end
return 0
"""

_CONSUME_OAUTH_SCRIPT = """
if redis.call('HGET', KEYS[1], 'binding') ~= ARGV[1] then return nil end
local verifier = redis.call('HGET', KEYS[1], 'verifier')
local return_to = redis.call('HGET', KEYS[1], 'return_to')
local session_id = redis.call('HGET', KEYS[1], 'session_id') or ''
redis.call('DEL', KEYS[1])
return {verifier, return_to, session_id}
"""


@dataclass(frozen=True)
class EmailChallenge:
    challenge_id: str
    code: str = field(repr=False)
    expires_at: datetime
    resend_after_seconds: int = 60


@dataclass(frozen=True)
class OAuthFlow:
    state: str = field(repr=False)
    binding: str = field(repr=False)
    verifier: str = field(repr=False)
    challenge: str
    return_to: str
    session_id: str = ""


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise ApplicationError("auth_dependency_unavailable")


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class VerificationStore:
    """Email rate limits and OAuth state; email proof authority lives in PostgreSQL."""

    def __init__(
        self,
        redis: Redis,
        hmac_key: str | None,
        *,
        key_prefix: str = "hotkey:identity:",
    ) -> None:
        self._redis = redis
        self._hmac_key = hmac_key.encode() if hmac_key else None
        self._prefix = key_prefix

    def _digest(self, *parts: str) -> str:
        if self._hmac_key is None:
            raise ApplicationError("auth_dependency_unavailable")
        payload = json.dumps(parts, separators=(",", ":"), ensure_ascii=True).encode()
        return hmac.new(self._hmac_key, payload, hashlib.sha256).hexdigest()

    def _key(self, kind: str, *parts: str) -> str:
        payload = json.dumps((kind, *parts), separators=(",", ":")).encode()
        return f"{self._prefix}{kind}:{hashlib.sha256(payload).hexdigest()}"

    def _eval(self, script: str, keys: list[str], arguments: Sequence[str | int]) -> object:
        try:
            values = [*keys, *(str(value) for value in arguments)]
            return cast(object, self._redis.eval(script, len(keys), *values))
        except (RedisError, OSError):
            raise ApplicationError("auth_dependency_unavailable") from None

    def _limit(self, keys: list[str], limits: list[int]) -> None:
        result = self._eval(_RATE_SCRIPT, keys, limits)
        if not isinstance(result, int):
            raise ApplicationError("auth_dependency_unavailable")
        if result:
            raise ApplicationError("auth_rate_limited", context={"retry_after_seconds": result})

    def limit_password(self, username: str, client_ip: str) -> None:
        # Reserve every attempt atomically before password verification, including successful ones.
        self._limit(
            [
                self._key("password-subject-ip", username.strip().casefold(), client_ip),
                self._key("password-ip", client_ip),
            ],
            [5, 900, 60, 3600],
        )

    def email_digest(self, *parts: str) -> bytes:
        """Key email proof digests with a server secret, never a plain code hash."""
        return bytes.fromhex(self._digest("email-v1", *parts))

    def limit_email_send(self, email: str, client_ip: str) -> None:
        """Reserve cooldown and send budgets without storing verification authority."""
        self._limit(
            [
                self._key("email-cooldown", email),
                self._key("email-send", email),
                self._key("email-send-ip", client_ip),
            ],
            [1, 60, 5, 3600, 20, 3600],
        )

    def limit_email_verify(self, client_ip: str) -> None:
        """Reserve every email verification request before accessing its proof."""
        self._limit([self._key("email-verify-ip", client_ip)], [60, 3600])

    def create_oauth_flow(self, return_to: str, *, session_id: str = "") -> OAuthFlow:
        verifier = secrets.token_urlsafe(64)
        flow = OAuthFlow(
            state=secrets.token_urlsafe(32),
            binding=secrets.token_urlsafe(32),
            verifier=verifier,
            challenge=_challenge(verifier),
            return_to=return_to,
            session_id=session_id,
        )
        key = self._key("oauth", flow.state)
        try:
            with self._redis.pipeline(transaction=True) as pipeline:
                pipeline.hset(
                    key,
                    mapping={
                        "binding": hashlib.sha256(flow.binding.encode()).hexdigest(),
                        "verifier": flow.verifier,
                        "return_to": return_to,
                        "session_id": session_id,
                    },
                )
                pipeline.expire(key, 300)
                pipeline.execute()
        except (RedisError, OSError):
            raise ApplicationError("auth_dependency_unavailable") from None
        return flow

    def consume_oauth_flow(self, state: str, binding: str) -> OAuthFlow:
        if not state or not binding or len(state) > 128 or len(binding) > 128:
            raise ApplicationError("invalid_oauth_state")
        result = self._eval(
            _CONSUME_OAUTH_SCRIPT,
            [self._key("oauth", state)],
            [hashlib.sha256(binding.encode()).hexdigest()],
        )
        if not isinstance(result, list) or len(result) != 3:
            raise ApplicationError("invalid_oauth_state")
        verifier, return_to, session_id = (_text(value) for value in result)
        return OAuthFlow(state, binding, verifier, _challenge(verifier), return_to, session_id)
