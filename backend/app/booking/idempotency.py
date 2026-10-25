from uuid import UUID

import asyncpg

from app.platform.errors import ApiError


async def try_claim(conn: asyncpg.Connection, user_id: UUID, key: str, req_hash: str) -> bool:
    """True if this call owns the key. A concurrent claimant makes this wait on the unique index
    until it commits (then we replay) or rolls back (then we proceed)."""
    row = await conn.fetchval(
        "INSERT INTO idempotency_keys (user_id, idem_key, request_hash, response_code, response_body)"
        " VALUES ($1, $2, $3, 0, '{}'::jsonb) ON CONFLICT DO NOTHING RETURNING 1",
        user_id,
        key,
        req_hash,
    )
    return row is not None


async def replay(
    conn: asyncpg.Connection, user_id: UUID, key: str, req_hash: str
) -> tuple[int, dict]:
    r = await conn.fetchrow(
        "SELECT request_hash, response_code, response_body FROM idempotency_keys"
        " WHERE user_id = $1 AND idem_key = $2",
        user_id,
        key,
    )
    if r is None or r["response_code"] == 0:  # should be impossible; ask the client to retry
        raise ApiError(503, "SERVICE_BUSY", "Please retry", headers={"Retry-After": "1"})
    if r["request_hash"] != req_hash:
        raise ApiError(
            422,
            "IDEMPOTENCY_KEY_REUSED",
            "This Idempotency-Key was used with a different request",
        )
    return r["response_code"], r["response_body"]


async def complete(
    conn: asyncpg.Connection,
    user_id: UUID,
    key: str,
    code: int,
    body: dict,
    booking_id: UUID | None,
) -> None:
    await conn.execute(
        "UPDATE idempotency_keys SET response_code = $3, response_body = $4, booking_id = $5"
        " WHERE user_id = $1 AND idem_key = $2",
        user_id,
        key,
        code,
        body,
        booking_id,
    )
