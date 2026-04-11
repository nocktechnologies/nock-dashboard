"""Redis-backed storage for OAuth clients and authorization codes.

Direct redis-py access rather than the Django cache framework because:
- No ``CACHES`` setting is configured in this project, and django-redis
  isn't a dep. Going direct keeps the install surface small.
- We want explicit, per-key TTLs (60s for codes, 30d for clients) —
  the Django cache abstraction lossily rounds TTLs.
- The operations here are trivial JSON get/set/delete, so the cache
  layer would just add indirection without buying anything.

Redis unavailability is turned into a typed ``StorageUnavailable``
exception the view layer can catch and convert to a clean OAuth
error response. Without this guard, a flapping Redis instance would
produce 500 tracebacks in the middle of the authorization flow and
claude.ai's connector would bail out with no useful diagnostics.
"""
from __future__ import annotations

import json
from typing import Any

import redis
from django.conf import settings


class StorageUnavailable(RuntimeError):
    """Raised when Redis is unreachable — view layer turns this into a 503."""


_CLIENT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days — re-register rarely
_CODE_TTL_SECONDS = 60  # 1 minute — enough for a redirect round-trip
_KEY_PREFIX = "nockcc:oauth:"


def _connect() -> redis.Redis:
    """Return a new redis client using the project's REDIS_URL."""
    url = getattr(settings, "CELERY_BROKER_URL", None) or getattr(
        settings, "REDIS_URL", "redis://localhost:6379/0",
    )
    return redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)


def _client_key(client_id: str) -> str:
    return f"{_KEY_PREFIX}client:{client_id}"


def _code_key(code: str) -> str:
    return f"{_KEY_PREFIX}code:{code}"


def put_client(client_id: str, record: dict[str, Any]) -> None:
    """Persist a registered OAuth client with a long TTL."""
    try:
        _connect().set(
            _client_key(client_id),
            json.dumps(record),
            ex=_CLIENT_TTL_SECONDS,
        )
    except redis.RedisError as exc:
        raise StorageUnavailable(str(exc)) from exc


def get_client(client_id: str) -> dict[str, Any] | None:
    try:
        raw = _connect().get(_client_key(client_id))
    except redis.RedisError as exc:
        raise StorageUnavailable(str(exc)) from exc
    if raw is None:
        return None
    return json.loads(raw)


def put_code(code: str, record: dict[str, Any]) -> None:
    """Persist an authorization code with a 60-second TTL."""
    try:
        _connect().set(_code_key(code), json.dumps(record), ex=_CODE_TTL_SECONDS)
    except redis.RedisError as exc:
        raise StorageUnavailable(str(exc)) from exc


def pop_code(code: str) -> dict[str, Any] | None:
    """Atomically fetch and delete an authorization code.

    Authorization codes are single-use per RFC 6749 §4.1.2 — a second
    attempt with the same code must fail, so we DELETE in the same
    pipeline as the GET. If the code doesn't exist (expired, already
    used, or never issued), returns ``None``.
    """
    try:
        r = _connect()
        key = _code_key(code)
        pipe = r.pipeline()
        pipe.get(key)
        pipe.delete(key)
        raw, _ = pipe.execute()
    except redis.RedisError as exc:
        raise StorageUnavailable(str(exc)) from exc
    if raw is None:
        return None
    return json.loads(raw)
