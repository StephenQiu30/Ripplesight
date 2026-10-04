from typing import cast
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import RedisError

from core.errors import ApplicationError
from publication.distribution_limits import PublicDistributionLimiter


class ControlledRedis:
    def __init__(self, result: object):
        self.result = result
        self.calls = []

    def eval(self, *args):
        self.calls.append(args)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize("result", [True, "0", None, -1, 61, RedisError("unavailable")])
def test_anonymous_rate_limit_fails_closed_for_unknown_redis_result(result):
    redis = ControlledRedis(result)
    with pytest.raises(ApplicationError, match="publication_distribution_unavailable"):
        PublicDistributionLimiter(cast(Redis, redis)).require_allowed(
            owner_id=uuid4(), peer="127.0.0.1"
        )


def test_one_atomic_window_binds_publisher_and_tcp_peer_without_storing_raw_address():
    owner = uuid4()
    redis = ControlledRedis(0)
    limiter = PublicDistributionLimiter(cast(Redis, redis))
    limiter.require_allowed(owner_id=owner, peer="127.0.0.1")
    args = redis.calls[0]
    assert args[1] == 1 and args[3:] == ("120", "60")
    assert "127.0.0.1" not in args[2]
    assert args[2] != limiter.key(uuid4(), "127.0.0.1")
    assert args[2] != limiter.key(owner, "127.0.0.2")
    redis.result = 60
    with pytest.raises(ApplicationError, match="publication_rate_limited") as error:
        limiter.require_allowed(owner_id=owner, peer="127.0.0.1")
    assert error.value.context == {"retry_after_seconds": 60}
