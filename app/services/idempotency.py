from __future__ import annotations

import hashlib
import json
from typing import Literal

from redis import Redis


LUA_CHECK_AND_SET = """
local key = KEYS[1]
local payload_hash = ARGV[1]
if redis.call('EXISTS', key) == 0 then
  redis.call('HSET', key, 'payload_hash', payload_hash)
  return 'set'
end
local existing = redis.call('HGET', key, 'payload_hash')
if existing == payload_hash then
  return 'match'
end
return 'conflict'
"""


class IdempotencyService:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def payload_hash(self, payload: dict) -> str:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def check_or_set(self, key: str, payload_hash: str) -> Literal["set", "match", "conflict"]:
        result = self.redis.eval(LUA_CHECK_AND_SET, 1, f"idempotency:{key}", payload_hash)
        return str(result)

    def bind_checkout(self, key: str, checkout_id: str) -> None:
        self.redis.hset(f"idempotency:{key}", "checkout_id", checkout_id)

    def get_checkout_id(self, key: str) -> str | None:
        return self.redis.hget(f"idempotency:{key}", "checkout_id")
