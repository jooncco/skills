"""Redis-backed pending queue shared with the worker."""
import json

import redis

from .config import settings

_client = redis.from_url(settings.redis_url)


def push(payload: dict) -> None:
    _client.lpush(settings.queue_key, json.dumps(payload))


def pop(timeout: int = 5) -> dict | None:
    item = _client.brpop(settings.queue_key, timeout=timeout)
    return json.loads(item[1]) if item else None


def depth() -> int:
    return _client.llen(settings.queue_key)
