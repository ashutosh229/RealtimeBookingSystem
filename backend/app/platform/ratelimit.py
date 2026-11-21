"""Live per-user admission control (ADR-0022): a token bucket in Redis, one token per booking request.

The same idea as the simulator's TokenBucket (allocation/admission.py), made shared across API
replicas by keeping the state in Redis. It never touches PostgreSQL, so a flood is refused before
it costs a transaction. Redis trouble fails open: booking correctness never depends on it (I3).
"""

import logging
import math
from uuid import UUID

from app.availability import cache as availability_cache
from app.platform.config import get_settings
from app.platform.errors import ApiError

log = logging.getLogger("rtbs.ratelimit")

# KEYS[1] bucket key; ARGV[1] tokens per second; ARGV[2] burst. Returns {allowed, wait_ms}.
# Time comes from Redis, so replicas with skewed clocks agree.
_LUA = """
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local d = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(d[1])
local ts = tonumber(d[2])
if tokens == nil then
  tokens = burst
  ts = now
end
tokens = math.min(burst, tokens + (now - ts) * rate / 1000)
local allowed = 0
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait = math.ceil((1 - tokens) * 1000 / rate)
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(burst / rate * 1000) + 1000)
return {allowed, wait}
"""


def _key(user_id: UUID) -> str:
    return f"rl:book:{user_id}"


async def check(user_id: UUID) -> None:
    """Take one token or raise 429 RATE_LIMITED. A no-op unless RATE_LIMIT_ENABLED is true."""
    s = get_settings()
    if not s.rate_limit_enabled or s.rate_limit_per_second <= 0 or s.rate_limit_burst < 1:
        return
    r = availability_cache.get_client()
    if r is None:
        return
    try:
        allowed, wait_ms = await r.eval(
            _LUA, 1, _key(user_id), str(s.rate_limit_per_second), str(s.rate_limit_burst)
        )
    except Exception:  # noqa: BLE001 - fail open, but say so
        log.warning("rate limiter unavailable, letting the request through", exc_info=True)
        return
    if int(allowed):
        return
    retry = max(1, math.ceil(int(wait_ms) / 1000))
    raise ApiError(
        429,
        "RATE_LIMITED",
        "Too many booking requests, slow down",
        details={"retry_after_seconds": retry},
        headers={"Retry-After": str(retry)},
    )
