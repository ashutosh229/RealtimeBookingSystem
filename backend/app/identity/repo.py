from datetime import datetime
from uuid import UUID

import asyncpg

_COLS = "user_id, email::text AS email, name, role::text AS role, user_group, is_active"


async def create_user(
    conn: asyncpg.Connection, email: str, name: str, pw_hash: str
) -> asyncpg.Record:
    return await conn.fetchrow(
        "INSERT INTO users (email, name, password_hash) VALUES ($1, $2, $3)"
        " RETURNING user_id, email::text AS email, name, role::text AS role, user_group",
        email,
        name,
        pw_hash,
    )


async def get_by_email(conn: asyncpg.Connection, email: str) -> asyncpg.Record | None:
    return await conn.fetchrow(f"SELECT {_COLS}, password_hash FROM users WHERE email = $1", email)


async def get_by_id(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(f"SELECT {_COLS} FROM users WHERE user_id = $1", user_id)


async def store_refresh(
    conn: asyncpg.Connection, token_hash: str, user_id: UUID, expires_at: datetime
) -> None:
    await conn.execute(
        "INSERT INTO refresh_tokens (token_hash, user_id, expires_at) VALUES ($1, $2, $3)",
        token_hash,
        user_id,
        expires_at,
    )


async def consume_refresh(conn: asyncpg.Connection, token_hash: str) -> UUID | None:
    """Atomic single-use: of two concurrent refreshes with one token, exactly one gets a row."""
    return await conn.fetchval(
        "UPDATE refresh_tokens SET revoked = true"
        " WHERE token_hash = $1 AND NOT revoked AND expires_at > now() RETURNING user_id",
        token_hash,
    )
