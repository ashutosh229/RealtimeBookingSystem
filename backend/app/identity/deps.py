import time
from uuid import UUID

import asyncpg
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.identity import repo, security
from app.platform.config import get_settings
from app.platform.db import get_conn
from app.platform.errors import ApiError

_bearer = HTTPBearer(auto_error=False)

# ADR-0024: optional per-process cache of the user row, so a request does not query PostgreSQL
# just to learn the role and group already in a verified token. Off unless USER_CACHE_SECONDS > 0.
# A role, group or deactivation change therefore reaches a replica after at most that many seconds.
_CACHE: dict[UUID, tuple[float, dict]] = {}
_CACHE_MAX = 10_000


def clear_user_cache() -> None:
    _CACHE.clear()


async def _load_user(conn: asyncpg.Connection, user_id: UUID) -> dict:
    ttl = get_settings().user_cache_seconds
    now = time.monotonic()
    if ttl > 0:
        hit = _CACHE.get(user_id)
        if hit is not None and hit[0] > now:
            return dict(hit[1])  # a copy: handlers must not be able to edit the cached row
    row = await repo.get_by_id(conn, user_id)
    if row is None or not row["is_active"]:
        _CACHE.pop(user_id, None)
        raise ApiError(401, "UNAUTHENTICATED", "Account unavailable")
    user = dict(row)
    if ttl > 0:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[user_id] = (now + ttl, user)
    return dict(user)


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn: asyncpg.Connection = Depends(get_conn),
) -> dict:
    if creds is None:
        raise ApiError(401, "UNAUTHENTICATED", "Missing credentials")
    claims = security.decode_access_token(creds.credentials)
    try:
        user_id = UUID(claims["sub"])
    except ValueError:
        raise ApiError(401, "UNAUTHENTICATED", "Invalid token") from None
    return await _load_user(conn, user_id)


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise ApiError(403, "FORBIDDEN", "Admin role required")
    return user
