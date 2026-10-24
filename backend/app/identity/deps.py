from uuid import UUID

import asyncpg
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.identity import repo, security
from app.platform.db import get_conn
from app.platform.errors import ApiError

_bearer = HTTPBearer(auto_error=False)


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
    user = await repo.get_by_id(conn, user_id)
    if user is None or not user["is_active"]:
        raise ApiError(401, "UNAUTHENTICATED", "Account unavailable")
    return dict(user)


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise ApiError(403, "FORBIDDEN", "Admin role required")
    return user
