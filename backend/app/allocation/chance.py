from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.allocation.metrics import chance_stats, percentile

_SQL = (
    "SELECT a.user_id, min(a.user_group) AS user_group, count(*) AS attempts,"
    " count(*) FILTER (WHERE a.outcome = 'CONFIRMED' OR b.confirmed_at IS NOT NULL) AS got"
    " FROM booking_attempts a LEFT JOIN bookings b ON b.booking_id = a.booking_id"
    " WHERE a.created_at >= $1 AND a.created_at <= $2"
    " AND ($3::uuid IS NULL OR a.resource_id = $3)"
    " GROUP BY a.user_id"
)  # a waitlisted attempt that was later promoted counts as a success; one still waiting does not


def histogram(chances: list[float]) -> list[int]:
    bins = [0] * 10
    for c in chances:
        bins[min(9, int(c * 10))] += 1
    return bins


async def summary(
    conn: asyncpg.Connection, *, resource_id: UUID | None, window_days: int, now: datetime
) -> dict:
    rows = await conn.fetch(_SQL, now - timedelta(days=window_days), now, resource_id)
    chances = [r["got"] / r["attempts"] for r in rows]
    groups: dict[str, list[float]] = {}
    for r, c in zip(rows, chances, strict=True):
        groups.setdefault(r["user_group"], []).append(c)
    return {
        "window_days": window_days,
        "users": len(rows),
        "attempts": sum(r["attempts"] for r in rows),
        **chance_stats(chances),
        "by_group": [
            {"user_group": g, "users": len(v), "mean_chance": sum(v) / len(v)}
            for g, v in sorted(groups.items())
        ],
        "histogram": histogram(chances),
    }


async def my_chance(
    conn: asyncpg.Connection, user_id: UUID, *, window_days: int, now: datetime
) -> dict:
    rows = await conn.fetch(_SQL, now - timedelta(days=window_days), now, None)
    chances = [r["got"] / r["attempts"] for r in rows]
    mine = next((r for r in rows if r["user_id"] == user_id), None)
    return {
        "window_days": window_days,
        "attempts": mine["attempts"] if mine else 0,
        "successes": mine["got"] if mine else 0,
        "my_chance": mine["got"] / mine["attempts"] if mine else None,
        "cohort_users": len(rows),
        "cohort_median": percentile(chances, 50) if chances else None,
        "cohort_mean": sum(chances) / len(chances) if chances else None,
    }
