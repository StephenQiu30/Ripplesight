"""One fail-closed Redis window across the anonymous distribution protocols."""

from hashlib import sha256
from typing import cast
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from core.errors import ApplicationError, DependencyUnavailableError

PUBLIC_DISTRIBUTION_REQUESTS = 120
PUBLIC_DISTRIBUTION_WINDOW_SECONDS = 60
_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]); ttl = tonumber(ARGV[2]) end
if count > tonumber(ARGV[1]) then return ttl end
return 0
"""


class PublicDistributionLimiter:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def key(owner_id: UUID, peer: str) -> str:
        return (
            f"hotkey:publication:distribution:v1:{owner_id.hex}:{sha256(peer.encode()).hexdigest()}"
        )

    def require_allowed(self, *, owner_id: UUID, peer: str) -> None:
        try:
            result = cast(
                object,
                self._client.eval(
                    _SCRIPT,
                    1,
                    self.key(owner_id, peer),
                    str(PUBLIC_DISTRIBUTION_REQUESTS),
                    str(PUBLIC_DISTRIBUTION_WINDOW_SECONDS),
                ),
            )
        except (RedisError, OSError):
            raise DependencyUnavailableError("publication_distribution_unavailable") from None
        if isinstance(result, bool) or not isinstance(result, int) or not 0 <= result <= 60:
            raise DependencyUnavailableError("publication_distribution_unavailable")
        if result:
            raise ApplicationError(
                "publication_rate_limited", context={"retry_after_seconds": result}
            )
