from datetime import datetime
from uuid import UUID

import asyncpg


async def count_active(
    conn: asyncpg.Connection, user_id: UUID, resource_id: UUID, now: datetime
) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM bookings WHERE user_id = $1 AND resource_id = $2"
        " AND status IN ('CONFIRMED','WAITLISTED') AND end_time > $3",
        user_id,
        resource_id,
        now,
    )


async def insert_booking(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    resource_id: UUID,
    start: datetime,
    end: datetime,
    quantity: int,
    status: str,
    exclusive: bool,
    key: str,
    req_hash: str,
    confirmed_at: datetime | None,
) -> asyncpg.Record:
    return await conn.fetchrow(
        "INSERT INTO bookings (user_id, resource_id, start_time, end_time, quantity, status,"
        " is_exclusive, idempotency_key, request_hash, confirmed_at)"
        " VALUES ($1, $2, $3, $4, $5, $6::booking_status, $7, $8, $9, $10)"
        " RETURNING booking_id, created_at",
        user_id,
        resource_id,
        start,
        end,
        quantity,
        status,
        exclusive,
        key,
        req_hash,
        confirmed_at,
    )


async def add_history(
    conn: asyncpg.Connection,
    booking_id: UUID,
    from_status: str | None,
    to_status: str,
    actor_id: UUID | None,
    reason: str,
) -> None:
    await conn.execute(
        "INSERT INTO booking_status_history (booking_id, from_status, to_status, actor_id, reason)"
        " VALUES ($1, $2::booking_status, $3::booking_status, $4, $5)",
        booking_id,
        from_status,
        to_status,
        actor_id,
        reason,
    )


async def add_allocation(
    conn: asyncpg.Connection,
    booking_id: UUID,
    policy_name: str,
    policy_version: str,
    decision: str,
    inputs: dict,
) -> None:
    await conn.execute(
        "INSERT INTO allocation_records (booking_id, policy_name, policy_version, decision_type, inputs)"
        " VALUES ($1, $2, $3, $4, $5)",
        booking_id,
        policy_name,
        policy_version,
        decision,
        inputs,
    )


async def add_waitlist(
    conn: asyncpg.Connection,
    *,
    booking_id: UUID,
    user_id: UUID,
    resource_id: UUID,
    start: datetime,
    end: datetime,
    quantity: int,
) -> asyncpg.Record:
    return await conn.fetchrow(
        "INSERT INTO waitlist_entries (booking_id, user_id, resource_id, start_time, end_time, quantity, expires_at)"
        " VALUES ($1, $2, $3, $4, $5, $6, $4) RETURNING waitlist_id, seq",
        booking_id,
        user_id,
        resource_id,
        start,
        end,
        quantity,
    )


async def waitlist_position(
    conn: asyncpg.Connection,
    resource_id: UUID,
    seq: int,
    start: datetime,
    end: datetime,
) -> int:
    """Arrival-order estimate among active entries that overlap this window."""
    return await conn.fetchval(
        "SELECT count(*) FROM waitlist_entries WHERE resource_id = $1 AND status = 'ACTIVE'"
        " AND seq <= $2 AND start_time < $4 AND end_time > $3",
        resource_id,
        seq,
        start,
        end,
    )
