import base64
import json
import math
from datetime import datetime
from uuid import UUID

import asyncpg

from app.platform.errors import ApiError

_SELECT = """
SELECT r.resource_id, r.type::text AS type, r.name, r.capacity, r.slot_minutes, r.open_time,
       r.close_time, r.timezone, r.max_slots_per_booking, r.max_quantity_per_booking,
       r.max_active_per_user, r.min_cancel_notice_minutes, r.booking_horizon_days,
       r.policy_name, r.lat, r.lon, r.active, r.version,
       COALESCE((SELECT array_agg(e.user_group ORDER BY e.user_group)
                 FROM resource_eligibility e WHERE e.resource_id = r.resource_id), '{}') AS eligible_groups
FROM resources r
"""

# Same columns plus the great-circle distance in metres from a point (Earth radius 6 371 km).
_SELECT_DIST = _SELECT.replace("FROM resources r", ", __DIST__ AS distance_m FROM resources r")


def _haversine(lat: str, lon: str) -> str:
    return (
        "2 * 6371000 * asin(sqrt("
        f"power(sin(radians(r.lat - {lat}) / 2), 2)"
        f" + cos(radians({lat})) * cos(radians(r.lat)) * power(sin(radians(r.lon - {lon}) / 2), 2)))"
    )


def encode_cursor(name: str, rid: UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([name, str(rid)]).encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        name, rid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return name, UUID(rid)
    except Exception:  # noqa: BLE001
        raise ApiError(422, "VALIDATION_ERROR", "invalid cursor") from None


async def get(conn: asyncpg.Connection, rid: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT + " WHERE r.resource_id = $1", rid)


async def get_for_update(conn: asyncpg.Connection, rid: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT + " WHERE r.resource_id = $1 FOR UPDATE OF r", rid)


async def get_for_share(conn: asyncpg.Connection, rid: UUID) -> asyncpg.Record | None:
    """Booking path: blocks against admin capacity changes and deactivation (which take FOR UPDATE)."""
    return await conn.fetchrow(_SELECT + " WHERE r.resource_id = $1 FOR SHARE OF r", rid)


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_page(
    conn: asyncpg.Connection,
    *,
    user: dict,
    type: str | None,
    q: str | None,
    eligible_only: bool,
    limit: int,
    cursor: str | None,
    near: tuple[float, float, int] | None = None,
    free_between: tuple[datetime, datetime] | None = None,
) -> tuple[list[asyncpg.Record], str | None]:
    """near = (lat, lon, radius_m): only resources within the radius, nearest first, one page (no cursor).
    free_between = (from, to): only resources with no fully booked slot overlapping [from, to)."""
    args: list = []
    where: list[str] = []

    def p(v) -> str:
        args.append(v)
        return f"${len(args)}"

    if user["role"] != "admin":
        where.append("r.active")
    if type:
        where.append(f"r.type = {p(type)}::resource_type")
    if q:
        where.append(f"r.name ILIKE '%' || {p(_like_escape(q))} || '%'")
    if eligible_only:
        where.append(
            "(NOT EXISTS (SELECT 1 FROM resource_eligibility e WHERE e.resource_id = r.resource_id)"
            " OR EXISTS (SELECT 1 FROM resource_eligibility e WHERE e.resource_id = r.resource_id"
            f" AND e.user_group = {p(user['user_group'])}))"
        )
    if free_between:
        lo, hi = free_between
        where.append(
            "NOT EXISTS (SELECT 1 FROM slot_usage s WHERE s.resource_id = r.resource_id"
            " AND s.used >= s.capacity"
            f" AND s.slot_start < {p(hi)}"
            f" AND s.slot_start + make_interval(mins => r.slot_minutes) > {p(lo)})"
        )
    if near:
        # Campus scale needs no PostGIS (HLD section 29 fallback): a bounding box narrows the rows,
        # then the haversine distance filters and orders them exactly.
        lat, lon, radius = near
        dlat = radius / 111_320
        dlon = radius / (111_320 * max(math.cos(math.radians(lat)), 0.01))
        dist = _haversine(p(lat), p(lon))
        where.append("r.lat IS NOT NULL AND r.lon IS NOT NULL")
        where.append(f"r.lat BETWEEN {p(lat - dlat)} AND {p(lat + dlat)}")
        where.append(f"r.lon BETWEEN {p(lon - dlon)} AND {p(lon + dlon)}")
        sql = "SELECT * FROM (" + _SELECT_DIST.replace("__DIST__", dist)
        sql += (" WHERE " + " AND ".join(where) if where else "") + ") x"
        sql += f" WHERE x.distance_m <= {p(radius)} ORDER BY x.distance_m, x.name LIMIT {p(limit)}"
        return await conn.fetch(sql, *args), None
    if cursor:
        name, rid = decode_cursor(cursor)
        where.append(f"(r.name, r.resource_id) > ({p(name)}, {p(rid)})")
    sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += f" ORDER BY r.name, r.resource_id LIMIT {p(limit + 1)}"
    rows = await conn.fetch(sql, *args)
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor(rows[-1]["name"], rows[-1]["resource_id"])
    return rows, next_cursor
