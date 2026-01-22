from __future__ import annotations

from redis import Redis


class Metrics:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def increment_success(self) -> None:
        self.redis.incr("metrics:checkout:success")

    def increment_retry(self) -> None:
        self.redis.incr("metrics:checkout:retry")

    def increment_failure(self) -> None:
        self.redis.incr("metrics:checkout:failure")

    def snapshot(self) -> dict[str, int]:
        return {
            "success_count": int(self.redis.get("metrics:checkout:success") or 0),
            "retry_count": int(self.redis.get("metrics:checkout:retry") or 0),
            "failure_count": int(self.redis.get("metrics:checkout:failure") or 0),
        }
