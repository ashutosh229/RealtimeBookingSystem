import base64
import json
from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.platform.errors import ApiError

_COLS = (
    "id, user_id, resource_id, start_time, end_time, quantity, waitlist_requested, outcome,"
    " reason, detail, http_status, booking_id, user_group, created_at"
)


def _enc(last_id: int) -> str:
    return base64.urlsafe_b64encode(json.dumps(last_id).encode()).decode()


def _dec(cursor: str) -> int:
    try:
        v = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if isinstance(v, int):
            return v
    except Exception:  # noqa: BLE001
        pass
    raise ApiError(422, "VALIDATION_ERROR", "invalid cursor")


async def list_attempts(
    conn: asyncpg.Connection,
    *,
    outcome: str | None,
    reason: str | None,
    resource_id: UUID | None,
    user_id: UUID | None,
    frm: datetime | None,
    to: datetime | None,
    limit: int,
    cursor: str | None,
):
    args: list = []
    where: list[str] = []

    def p(v) -> str:
        args.append(v)
        return f"${len(args)}"

    if outcome:
        where.append(f"outcome = {p(outcome)}")
    if reason:
        where.append(f"reason = {p(reason)}")
    if resource_id:
        where.append(f"resource_id = {p(resource_id)}")
    if user_id:
        where.append(f"user_id = {p(user_id)}")
    if frm:
        where.append(f"created_at >= {p(frm)}")
    if to:
        where.append(f"created_at < {p(to)}")
    if cursor:
        where.append(f"id < {p(_dec(cursor))}")
    sql = f"SELECT {_COLS} FROM booking_attempts"
    sql += (
        " WHERE " + " AND ".join(where) if where else ""
    ) + f" ORDER BY id DESC LIMIT {p(limit + 1)}"
    rows = await conn.fetch(sql, *args)
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = _enc(rows[-1]["id"])
    return rows, nxt


async def rejection_summary(
    conn: asyncpg.Connection,
    *,
    resource_id: UUID | None,
    window_days: int,
    now: datetime,
) -> dict:
    start = now - timedelta(days=window_days)
    scope = (
        " WHERE created_at >= $1 AND created_at <= $2 AND ($3::uuid IS NULL OR resource_id = $3)"
    )
    a = (start, now, resource_id)
    by_outcome = {
        r["outcome"]: r["n"]
        for r in await conn.fetch(
            f"SELECT outcome, count(*) AS n FROM booking_attempts{scope} GROUP BY outcome",
            *a,
        )
    }
    by_reason = {
        r["reason"]: r["n"]
        for r in await conn.fetch(
            f"SELECT reason, count(*) AS n FROM booking_attempts{scope} AND outcome = 'REJECTED'"
            " GROUP BY reason ORDER BY n DESC",
            *a,
        )
    }
    groups = await conn.fetch(
        "SELECT user_group, count(*) AS attempts, count(*) FILTER (WHERE outcome = 'REJECTED') AS rejected"
        f" FROM booking_attempts{scope} GROUP BY user_group ORDER BY user_group",
        *a,
    )
    hours = {
        r["h"]: r["n"]
        for r in await conn.fetch(
            "SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC')::int AS h, count(*) AS n"
            f" FROM booking_attempts{scope} AND outcome = 'REJECTED' GROUP BY h",
            *a,
        )
    }
    users_rejected = await conn.fetchval(
        f"SELECT count(DISTINCT user_id) FROM booking_attempts{scope} AND outcome = 'REJECTED'",
        *a,
    )
    confirmed, waitlisted = by_outcome.get("CONFIRMED", 0), by_outcome.get("WAITLISTED", 0)
    rejected = by_outcome.get("REJECTED", 0)
    attempts = confirmed + waitlisted + rejected
    return {
        "window_days": window_days,
        "attempts": attempts,
        "confirmed": confirmed,
        "waitlisted": waitlisted,
        "rejected": rejected,
        "rejection_rate": rejected / attempts if attempts else 0.0,
        "users_rejected": users_rejected,
        "by_reason": by_reason,
        "by_group": [
            {
                "user_group": g["user_group"],
                "attempts": g["attempts"],
                "rejected": g["rejected"],
                "rejection_rate": (g["rejected"] / g["attempts"] if g["attempts"] else 0.0),
            }
            for g in groups
        ],
        "by_hour_utc": [hours.get(h, 0) for h in range(24)],
    }
