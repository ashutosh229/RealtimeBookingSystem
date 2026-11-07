from datetime import datetime
from uuid import UUID

import asyncpg


async def lock_waiting(
    conn: asyncpg.Connection, resource_id: UUID, now: datetime
) -> list[asyncpg.Record]:
    """Active waitlist entries for a resource. Locks the BOOKING rows (same order as cancel: booking
    first, waitlist entry second) and skips rows another transaction holds."""
    return await conn.fetch(
        "SELECT b.booking_id, b.user_id, b.start_time, b.end_time, b.quantity, b.created_at,"
        "       w.seq, u.user_group, u.is_active"
        " FROM bookings b"
        " JOIN waitlist_entries w ON w.booking_id = b.booking_id"
        " JOIN users u ON u.user_id = b.user_id"
        " WHERE b.resource_id = $1 AND b.status = 'WAITLISTED' AND w.status = 'ACTIVE' AND w.expires_at > $2"
        " ORDER BY b.booking_id FOR UPDATE OF b SKIP LOCKED",
        resource_id,
        now,
    )


async def recent_counts(
    conn: asyncpg.Connection, user_ids: list[UUID], resource_type: str, since: datetime
) -> dict[UUID, int]:
    """Allocations per user inside the rolling window, across resources of the same type.
    A booking cancelled less than an hour before it started still counts, so book-and-cancel
    cycling does not reset a user's usage."""
    rows = await conn.fetch(
        "SELECT b.user_id, count(*) AS n FROM bookings b JOIN resources r ON r.resource_id = b.resource_id"
        " WHERE b.user_id = ANY($1::uuid[]) AND r.type = $2::resource_type AND b.confirmed_at >= $3"
        "   AND (b.status IN ('CONFIRMED','COMPLETED')"
        "        OR (b.status = 'CANCELLED' AND b.start_time - b.cancelled_at < interval '1 hour'))"
        " GROUP BY b.user_id",
        user_ids,
        resource_type,
        since,
    )
    return {r["user_id"]: r["n"] for r in rows}


async def add_skip_once(
    conn: asyncpg.Connection,
    booking_id: UUID,
    policy_name: str,
    policy_version: str,
    inputs: dict,
    reason: str,
) -> None:
    """Record SKIP_INELIGIBLE at most once per booking and reason (the promoter runs repeatedly)."""
    await conn.execute(
        "INSERT INTO allocation_records (booking_id, policy_name, policy_version, decision_type, inputs, reason)"
        " SELECT $1::uuid, $2::text, $3::text, 'SKIP_INELIGIBLE', $4::jsonb, $5::text"
        " WHERE NOT EXISTS (SELECT 1 FROM allocation_records WHERE booking_id = $1"
        "                   AND decision_type = 'SKIP_INELIGIBLE' AND reason = $5)",
        booking_id,
        policy_name,
        policy_version,
        inputs,
        reason,
    )


async def recent_contended_counts(
    conn: asyncpg.Connection,
    user_ids: list[UUID],
    resource_type: str,
    since: datetime,
    min_waiting: int,
) -> dict[UUID, int]:
    """Wins gained through the waitlist while at least `min_waiting` others were still queued."""
    rows = await conn.fetch(
        "SELECT b.user_id, count(*) AS n FROM allocation_records a"
        " JOIN bookings b ON b.booking_id = a.booking_id"
        " JOIN resources r ON r.resource_id = b.resource_id"
        " WHERE a.decision_type = 'PROMOTE' AND b.user_id = ANY($1::uuid[])"
        " AND r.type = $2::resource_type AND b.confirmed_at >= $3"
        " AND COALESCE((a.inputs->>'waiting_after')::int, 0) >= $4"
        " AND (b.status IN ('CONFIRMED','COMPLETED')"
        "      OR (b.status = 'CANCELLED' AND b.start_time - b.cancelled_at < interval '1 hour'))"
        " GROUP BY b.user_id",
        user_ids,
        resource_type,
        since,
        min_waiting,
    )
    return {r["user_id"]: r["n"] for r in rows}


async def users_with_recent_win(
    conn: asyncpg.Connection, user_ids: list[UUID], resource_type: str, since: datetime
) -> list[UUID]:
    """Users allocated a slot of this resource type after `since` (same booking filter as recent_counts)."""
    rows = await conn.fetch(
        "SELECT DISTINCT b.user_id FROM bookings b JOIN resources r ON r.resource_id = b.resource_id"
        " WHERE b.user_id = ANY($1::uuid[]) AND r.type = $2::resource_type AND b.confirmed_at > $3"
        "   AND (b.status IN ('CONFIRMED','COMPLETED')"
        "        OR (b.status = 'CANCELLED' AND b.start_time - b.cancelled_at < interval '1 hour'))",
        user_ids,
        resource_type,
        since,
    )
    return [r["user_id"] for r in rows]


async def win_ages(
    conn: asyncpg.Connection,
    user_ids: list[UUID],
    resource_type: str,
    since: datetime,
    now: datetime,
) -> dict[UUID, list[float]]:
    """Ages in days of each user's wins inside the window (same booking filter as recent_counts)."""
    rows = await conn.fetch(
        "SELECT b.user_id,"
        " array_agg((EXTRACT(EPOCH FROM ($4::timestamptz - b.confirmed_at)) / 86400.0)::float8"
        "           ORDER BY b.confirmed_at) AS ages"
        " FROM bookings b JOIN resources r ON r.resource_id = b.resource_id"
        " WHERE b.user_id = ANY($1::uuid[]) AND r.type = $2::resource_type AND b.confirmed_at >= $3"
        "   AND (b.status IN ('CONFIRMED','COMPLETED')"
        "        OR (b.status = 'CANCELLED' AND b.start_time - b.cancelled_at < interval '1 hour'))"
        " GROUP BY b.user_id",
        user_ids,
        resource_type,
        since,
        now,
    )
    return {r["user_id"]: [float(a) for a in r["ages"]] for r in rows}
