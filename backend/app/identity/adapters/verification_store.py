from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

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

_SEND_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return math.max(1, redis.call('TTL', KEYS[1]))
end
if tonumber(redis.call('GET', KEYS[2]) or '0') >= 5 then
  return math.max(1, redis.call('TTL', KEYS[2]))
end
if tonumber(redis.call('GET', KEYS[3]) or '0') >= 20 then
  return math.max(1, redis.call('TTL', KEYS[3]))
end
redis.call('SET', KEYS[1], '1', 'EX', 60)
for i=2,3 do
  if redis.call('INCR', KEYS[i]) == 1 then redis.call('EXPIRE', KEYS[i], 3600) end
end
local previous = redis.call('GET', KEYS[5])
if previous then redis.call('DEL', previous) end
redis.call('HSET', KEYS[4], 'email', ARGV[1], 'digest', ARGV[2],
  'purpose', ARGV[3], 'user_id', ARGV[4], 'attempts', 0)
redis.call('EXPIRE', KEYS[4], 300)
redis.call('SET', KEYS[5], KEYS[4], 'EX', 300)
return 0
"""

_CONSUME_EMAIL_SCRIPT = """
if tonumber(redis.call('GET', KEYS[2]) or '0') >= 60 then
  return {'limited', tostring(math.max(1, redis.call('TTL', KEYS[2])))}
end
if redis.call('INCR', KEYS[2]) == 1 then redis.call('EXPIRE', KEYS[2], 3600) end
if redis.call('EXISTS', KEYS[1]) == 0 then return {'invalid'} end
local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
if attempts > 5 then redis.call('DEL', KEYS[1]); return {'invalid'} end
if redis.call('HGET', KEYS[1], 'purpose') ~= ARGV[2]
  or redis.call('HGET', KEYS[1], 'user_id') ~= ARGV[3]
  or redis.call('HGET', KEYS[1], 'email') ~= ARGV[4]
  or redis.call('HGET', KEYS[1], 'digest') ~= ARGV[1] then
  if attempts >= 5 then redis.call('DEL', KEYS[1]) end
  return {'invalid'}
end
local email = redis.call('HGET', KEYS[1], 'email')
redis.call('DEL', KEYS[1])
return {'ok', email}
"""

_CONSUME_OAUTH_SCRIPT = """
if redis.call('HGET', KEYS[1], 'binding') ~= ARGV[1] then return nil end
local verifier = redis.call('HGET', KEYS[1], 'verifier')
local return_to = redis.call('HGET', KEYS[1], 'return_to')
redis.call('DEL', KEYS[1])
return {verifier, return_to}
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


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise ApplicationError("auth_dependency_unavailable")


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class VerificationStore:
    """Atomic, fail-closed verification; no OTP or subject appears in a Redis key."""

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

    def send_email_challenge(
        self,
        email: str,
        client_ip: str,
        purpose: str = "login",
        user_id: str | None = None,
    ) -> EmailChallenge:
        normalized = email.strip().lower()
        challenge_id = str(uuid4())
        code = f"{secrets.randbelow(1_000_000):06d}"
        owner = user_id or ""
        digest = self._digest("otp", challenge_id, normalized, purpose, owner, code)
        result = self._eval(
            _SEND_SCRIPT,
            [
                self._key("email-cooldown", normalized),
                self._key("email-send", normalized),
                self._key("email-send-ip", client_ip),
                self._key("email-challenge", challenge_id),
                self._key("email-latest", normalized, purpose, owner),
            ],
            [normalized, digest, purpose, owner],
        )
        if not isinstance(result, int):
            raise ApplicationError("auth_dependency_unavailable")
        if result:
            raise ApplicationError("auth_rate_limited", context={"retry_after_seconds": result})
        return EmailChallenge(challenge_id, code, datetime.now(UTC) + timedelta(seconds=300))

    def invalidate_email_challenge(self, challenge_id: str) -> None:
        try:
            self._redis.delete(self._key("email-challenge", challenge_id))
        except (RedisError, OSError):
            raise ApplicationError("auth_dependency_unavailable") from None

    def consume_email_challenge(
        self,
        challenge_id: str,
        code: str,
        client_ip: str,
        purpose: str = "login",
        user_id: str | None = None,
    ) -> str:
        owner = user_id or ""
        key = self._key("email-challenge", challenge_id)
        try:
            email_value = self._redis.hget(key, "email")
        except (RedisError, OSError):
            raise ApplicationError("auth_dependency_unavailable") from None
        email = _text(email_value) if email_value is not None else ""
        result = self._eval(
            _CONSUME_EMAIL_SCRIPT,
            [key, self._key("email-verify-ip", client_ip)],
            [self._digest("otp", challenge_id, email, purpose, owner, code), purpose, owner, email],
        )
        if not isinstance(result, list) or not result:
            raise ApplicationError("auth_dependency_unavailable")
        status = _text(result[0])
        if status == "limited" and len(result) == 2:
            raise ApplicationError(
                "auth_rate_limited", context={"retry_after_seconds": int(_text(result[1]))}
            )
        if status != "ok" or len(result) != 2:
            raise ApplicationError("invalid_email_code")
        return _text(result[1])

    def create_oauth_flow(self, return_to: str) -> OAuthFlow:
        verifier = secrets.token_urlsafe(64)
        flow = OAuthFlow(
            state=secrets.token_urlsafe(32),
            binding=secrets.token_urlsafe(32),
            verifier=verifier,
            challenge=_challenge(verifier),
            return_to=return_to,
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
        if not isinstance(result, list) or len(result) != 2:
            raise ApplicationError("invalid_oauth_state")
        verifier, return_to = (_text(value) for value in result)
        return OAuthFlow(state, binding, verifier, _challenge(verifier), return_to)
