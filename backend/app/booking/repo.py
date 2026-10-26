import base64
import json
from datetime import datetime
from uuid import UUID

import asyncpg

from app.platform.errors import ApiError

_LOCKED = """
SELECT b.booking_id, b.user_id, b.resource_id, b.start_time, b.end_time, b.quantity,
       b.status::text AS status, r.slot_minutes, r.min_cancel_notice_minutes
FROM bookings b JOIN resources r ON r.resource_id = b.resource_id
"""

_VIEW = """
SELECT b.booking_id, b.user_id, b.status::text AS status, b.resource_id, b.start_time, b.end_time,
       b.quantity, b.created_at, w.waitlist_id,
       CASE WHEN b.status = 'WAITLISTED' THEN w.expires_at END AS expires_at,
       CASE WHEN w.status = 'ACTIVE' THEN (
           SELECT count(*) FROM waitlist_entries x
           WHERE x.resource_id = w.resource_id AND x.status = 'ACTIVE' AND x.seq <= w.seq
             AND x.start_time < w.end_time AND x.end_time > w.start_time) END AS waitlist_position
FROM bookings b LEFT JOIN waitlist_entries w ON w.booking_id = b.booking_id
"""


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


async def get_for_update(conn: asyncpg.Connection, bid: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_LOCKED + " WHERE b.booking_id = $1 FOR UPDATE OF b", bid)


async def active_for_resource_for_update(
    conn: asyncpg.Connection, rid: UUID, now: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(
        _LOCKED + " WHERE b.resource_id = $1 AND b.status IN ('CONFIRMED','WAITLISTED')"
        " AND b.end_time > $2 ORDER BY b.booking_id FOR UPDATE OF b",
        rid,
        now,
    )


async def mark_cancelled(conn: asyncpg.Connection, bid: UUID, now: datetime) -> None:
    await conn.execute(
        "UPDATE bookings SET status = 'CANCELLED', cancelled_at = $2, updated_at = $2,"
        " version = version + 1 WHERE booking_id = $1",
        bid,
        now,
    )


async def cancel_waitlist_entry(conn: asyncpg.Connection, bid: UUID) -> None:
    await conn.execute(
        "UPDATE waitlist_entries SET status = 'CANCELLED' WHERE booking_id = $1 AND status = 'ACTIVE'",
        bid,
    )


async def get_view(conn: asyncpg.Connection, bid: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_VIEW + " WHERE b.booking_id = $1", bid)


async def history(conn: asyncpg.Connection, bid: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT from_status::text AS from_status, to_status::text AS to_status, reason, created_at"
        " FROM booking_status_history WHERE booking_id = $1 ORDER BY id",
        bid,
    )


def _encode_cursor(start: datetime, bid: UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([start.isoformat(), str(bid)]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        s, b = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(s), UUID(b)
    except Exception:  # noqa: BLE001
        raise ApiError(422, "VALIDATION_ERROR", "invalid cursor") from None


async def list_for_user(
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    status: str | None,
    frm: datetime | None,
    to: datetime | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[asyncpg.Record], str | None]:
    args: list = [user_id]
    where = ["b.user_id = $1"]

    def p(v) -> str:
        args.append(v)
        return f"${len(args)}"

    if status:
        where.append(f"b.status = {p(status)}::booking_status")
    if frm:
        where.append(f"b.start_time >= {p(frm)}")
    if to:
        where.append(f"b.start_time < {p(to)}")
    if cursor:
        st, bid = _decode_cursor(cursor)
        where.append(f"(b.start_time, b.booking_id) < ({p(st)}, {p(bid)})")
    sql = _VIEW + " WHERE " + " AND ".join(where)
    sql += f" ORDER BY b.start_time DESC, b.booking_id DESC LIMIT {p(limit + 1)}"
    rows = await conn.fetch(sql, *args)
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = _encode_cursor(rows[-1]["start_time"], rows[-1]["booking_id"])
    return rows, nxt


async def mark_promoted(conn: asyncpg.Connection, bid: UUID, now: datetime) -> None:
    done = await conn.execute(
        "UPDATE bookings SET status = 'CONFIRMED', confirmed_at = $2, updated_at = $2, version = version + 1"
        " WHERE booking_id = $1 AND status = 'WAITLISTED'",
        bid,
        now,
    )
    if done != "UPDATE 1":
        raise RuntimeError(f"booking {bid} was not WAITLISTED at promotion")
    await conn.execute(
        "UPDATE waitlist_entries SET status = 'PROMOTED', promoted_at = $2"
        " WHERE booking_id = $1 AND status = 'ACTIVE'",
        bid,
        now,
    )
