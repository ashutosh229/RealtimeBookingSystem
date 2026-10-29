from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg

from app.allocation.metrics import jain_index
from app.resources import slots


async def summary(
    conn: asyncpg.Connection, *, resource_id: UUID | None, window_days: int, now: datetime
) -> dict:
    start = now - timedelta(days=window_days)

    # Capacity-units that have existed in the window: slots already started x capacity, per resource.
    cap_units = 0
    for r in await conn.fetch(
        "SELECT capacity, slot_minutes, open_time, close_time, timezone, created_at FROM resources"
        " WHERE ($1::uuid IS NULL OR resource_id = $1)",
        resource_id,
    ):
        lo, z = max(start, r["created_at"]), ZoneInfo(r["timezone"])
        day, last = lo.astimezone(z).date(), now.astimezone(z).date()
        while day <= last:
            cap_units += r["capacity"] * sum(1 for s in slots.day_slots(r, day) if lo <= s < now)
            day += timedelta(days=1)
    used = await conn.fetchval(
        "SELECT COALESCE(SUM(used), 0) FROM slot_usage WHERE slot_start >= $1 AND slot_start < $2"
        " AND ($3::uuid IS NULL OR resource_id = $3)",
        start,
        now,
        resource_id,
    )
    utilization = min(1.0, used / cap_units) if cap_units else 0.0

    # Fairness: users who created a booking in the window; x = how many of their bookings were ever confirmed.
    got = await conn.fetch(
        "SELECT count(*) FILTER (WHERE confirmed_at IS NOT NULL) AS got FROM bookings"
        " WHERE created_at >= $1 AND created_at <= $2 AND ($3::uuid IS NULL OR resource_id = $3)"
        " GROUP BY user_id",
        start,
        now,
        resource_id,
    )
    waiting = await conn.fetchval(
        "SELECT count(*) FROM waitlist_entries WHERE status = 'ACTIVE' AND ($1::uuid IS NULL OR resource_id = $1)",
        resource_id,
    )
    w = await conn.fetchrow(
        "SELECT COALESCE(avg(t.w), 0)::float8 AS mean,"
        "       COALESCE(percentile_disc(0.95) WITHIN GROUP (ORDER BY t.w), 0)::float8 AS p95,"
        "       COALESCE(max(t.w), 0)::float8 AS max"
        " FROM (SELECT EXTRACT(EPOCH FROM (confirmed_at - created_at))::float8 AS w FROM bookings"
        "       WHERE confirmed_at IS NOT NULL AND created_at >= $1 AND created_at <= $2"
        "       AND ($3::uuid IS NULL OR resource_id = $3)) t",
        start,
        now,
        resource_id,
    )
    return {
        "window_days": window_days,
        "utilization": utilization,
        "jain_index": jain_index(r["got"] for r in got),
        "waitlist_length": waiting,
        "wait_seconds": {"mean": w["mean"], "p95": w["p95"], "max": w["max"]},
    }
