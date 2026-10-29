import base64
import json
from datetime import datetime
from uuid import UUID

import asyncpg

from app.platform.errors import ApiError

_ENTRY = """
SELECT w.waitlist_id, w.booking_id, w.user_id, w.resource_id, w.status::text AS status,
       w.start_time, w.end_time, w.seq, r.policy_name,
       CASE WHEN w.status = 'ACTIVE' THEN (
           SELECT count(*) FROM waitlist_entries x
           WHERE x.resource_id = w.resource_id AND x.status = 'ACTIVE' AND x.seq <= w.seq
             AND x.start_time < w.end_time AND x.end_time > w.start_time) END AS position
FROM waitlist_entries w JOIN resources r ON r.resource_id = w.resource_id
"""


def _enc(value) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def _dec(cursor: str):
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception:  # noqa: BLE001
        raise ApiError(422, "VALIDATION_ERROR", "invalid cursor") from None


def entry_dict(row: asyncpg.Record) -> dict:
    d = dict(row)
    # Under FAIR_SHARE the real order changes with every promotion, so the arrival-order position is an estimate.
    d["position_is_estimate"] = d["position"] is not None and d["policy_name"] == "FAIR_SHARE"
    return d


async def get_entry(conn: asyncpg.Connection, waitlist_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_ENTRY + " WHERE w.waitlist_id = $1", waitlist_id)


async def list_active(
    conn: asyncpg.Connection, resource_id: UUID | None, limit: int, cursor: str | None
):
    args: list = []
    where = ["w.status = 'ACTIVE'"]
    if resource_id:
        args.append(resource_id)
        where.append(f"w.resource_id = ${len(args)}")
    if cursor:
        seq = _dec(cursor)
        if not isinstance(seq, int):
            raise ApiError(422, "VALIDATION_ERROR", "invalid cursor")
        args.append(seq)
        where.append(f"w.seq > ${len(args)}")
    args.append(limit + 1)
    rows = await conn.fetch(
        _ENTRY + " WHERE " + " AND ".join(where) + f" ORDER BY w.seq LIMIT ${len(args)}",
        *args,
    )
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = _enc(rows[-1]["seq"])
    return rows, nxt


async def list_allocations(
    conn: asyncpg.Connection,
    resource_id: UUID | None,
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

    if resource_id:
        where.append(f"b.resource_id = {p(resource_id)}")
    if frm:
        where.append(f"a.decided_at >= {p(frm)}")
    if to:
        where.append(f"a.decided_at < {p(to)}")
    if cursor:
        last = _dec(cursor)
        if not isinstance(last, int):
            raise ApiError(422, "VALIDATION_ERROR", "invalid cursor")
        where.append(f"a.id < {p(last)}")
    sql = (
        "SELECT a.id, a.booking_id, a.policy_name, a.policy_version, a.decision_type, a.inputs, a.reason,"
        " a.decided_at FROM allocation_records a JOIN bookings b ON b.booking_id = a.booking_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + f" ORDER BY a.id DESC LIMIT {p(limit + 1)}"
    )
    rows = await conn.fetch(sql, *args)
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = _enc(rows[-1]["id"])
    return rows, nxt
