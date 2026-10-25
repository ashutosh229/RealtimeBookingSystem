import base64
import json
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
) -> tuple[list[asyncpg.Record], str | None]:
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
