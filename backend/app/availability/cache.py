"""Availability read cache (LLD section 25). Advisory only: booking never reads it (I3)."""

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from uuid import UUID

import redis.asyncio as aioredis

from app.platform.config import get_settings

log = logging.getLogger("rtbs.cache")
Loader = Callable[[], Awaitable[tuple[dict, bool]]]  # returns (data, cacheable)
_client: aioredis.Redis | None = None


async def init(url: str | None = None) -> None:
    global _client
    _client = aioredis.from_url(
        url or get_settings().redis_url,
        decode_responses=True,
        socket_timeout=0.5,
        socket_connect_timeout=0.5,
    )


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_client() -> aioredis.Redis | None:
    return _client


def _ver_key(rid) -> str:
    return f"avail:ver:{rid}"


def _key(rid, day: str, ver: int) -> str:
    return f"avail:{rid}:{day}:v{ver}"


def _ttl_ms() -> int:
    return int(get_settings().avail_ttl_seconds * 1000 * random.uniform(0.8, 1.2))


def _default(o):
    if isinstance(o, datetime | date):
        return o.isoformat()
    if isinstance(o, UUID):
        return str(o)
    raise TypeError(f"cannot serialise {type(o)}")


async def bump(rid, *, strict: bool = False) -> None:
    """Invalidate every cached view of a resource. Call AFTER the change committed.
    strict=True (the event consumer) raises on failure so the message is retried."""
    r = _client
    if r is None:
        if strict:
            raise RuntimeError("cache is not configured")
        return
    try:
        async with r.pipeline(transaction=True) as p:
            p.incr(_ver_key(rid))
            p.expire(_ver_key(rid), 86400)  # far longer than any entry's TTL
            await p.execute()
    except Exception:
        log.warning("could not invalidate the cache for %s", rid, exc_info=True)
        if strict:
            raise


async def cached(rid: str, day: str, loader: Loader) -> tuple[dict, str]:
    """Returns (data, 'HIT' | 'MISS' | 'BYPASS'). Errors raised by `loader` propagate unchanged."""
    r = _client
    if r is None:
        data, _ = await loader()
        return data, "BYPASS"
    owner = False
    try:
        ver = int(
            await r.get(_ver_key(rid)) or 0
        )  # read BEFORE the database (version-stamped fill)
        key = _key(rid, day, ver)
        raw = await r.get(key)
        if raw is not None:
            return json.loads(raw), "HIT"
        lock = f"lock:avail:{rid}:{day}"
        owner = bool(await r.set(lock, "1", nx=True, px=2000))  # single-flight
        if not owner:
            for _ in range(3):
                await asyncio.sleep(0.05)
                raw = await r.get(key)
                if raw is not None:
                    return json.loads(raw), "HIT"
    except Exception:
        log.warning("redis unavailable, reading the database", exc_info=True)
        data, _ = await loader()
        return data, "BYPASS"
    try:
        data, cacheable = await loader()
        if owner and cacheable:
            try:
                await r.set(key, json.dumps(data, default=_default), px=_ttl_ms())
            except Exception:
                log.warning("could not fill the cache", exc_info=True)
        return data, "MISS"
    finally:
        if owner:
            try:
                await r.delete(lock)
            except Exception:  # noqa: BLE001
                pass
