from datetime import UTC, datetime, timedelta

import asyncpg

from app.identity import repo, security
from app.platform.config import get_settings
from app.platform.errors import ApiError

_BAD_LOGIN = ApiError(401, "INVALID_CREDENTIALS", "Invalid email or password")


async def register(
    conn: asyncpg.Connection, email: str, name: str, password: str
) -> asyncpg.Record:
    pw_hash = await security.hash_password(password)
    try:
        return await repo.create_user(conn, email, name, pw_hash)
    except asyncpg.UniqueViolationError:
        raise ApiError(409, "EMAIL_TAKEN", "Email already registered") from None


async def issue_tokens(conn: asyncpg.Connection, user: asyncpg.Record) -> dict:
    s = get_settings()
    raw, hashed = security.new_refresh_token()
    await repo.store_refresh(
        conn,
        hashed,
        user["user_id"],
        datetime.now(UTC) + timedelta(days=s.refresh_ttl_days),
    )
    return {
        "access_token": security.create_access_token(
            user["user_id"], user["role"], user["user_group"]
        ),
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": s.access_ttl_minutes * 60,
    }


async def login(conn: asyncpg.Connection, email: str, password: str) -> dict:
    user = await repo.get_by_email(conn, email)
    if user is None:
        await security.verify_dummy(password)
        raise _BAD_LOGIN
    if not await security.verify_password(password, user["password_hash"]) or not user["is_active"]:
        raise _BAD_LOGIN
    return await issue_tokens(conn, user)


async def refresh(conn: asyncpg.Connection, raw_token: str) -> dict:
    async with conn.transaction():
        uid = await repo.consume_refresh(conn, security.hash_refresh(raw_token))
        user = await repo.get_by_id(conn, uid) if uid else None
        if user is None or not user["is_active"]:
            raise ApiError(401, "UNAUTHENTICATED", "Invalid refresh token")
        return await issue_tokens(conn, user)
