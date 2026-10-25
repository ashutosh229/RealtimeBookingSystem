from collections.abc import Mapping
from datetime import UTC, date, datetime

import asyncpg

from app.platform.errors import ApiError
from app.resources import slots


async def get_availability(
    conn: asyncpg.Connection,
    res: Mapping,
    *,
    day: date | None,
    frm: datetime | None,
    to: datetime | None,
) -> dict:
    """Authoritative read straight from the ledger. The Redis layer wraps this in Phase 4."""
    if day and (frm or to):
        raise ApiError(422, "VALIDATION_ERROR", "use either 'date' or 'from'+'to', not both")
    if day:
        starts = slots.day_slots(res, day)
    elif frm and to:
        starts = slots.range_slots(res, frm, to)
    else:
        raise ApiError(422, "VALIDATION_ERROR", "provide 'date' or both 'from' and 'to'")
    rows = await conn.fetch(
        "SELECT g.slot_start, COALESCE(u.used, 0) AS used"
        " FROM unnest($2::timestamptz[]) AS g(slot_start)"
        " LEFT JOIN slot_usage u ON u.resource_id = $1 AND u.slot_start = g.slot_start"
        " ORDER BY g.slot_start",
        res["resource_id"],
        starts,
    )
    cap = res["capacity"]
    return {
        "resource_id": res["resource_id"],
        "as_of": datetime.now(UTC),
        "slot_minutes": res["slot_minutes"],
        "slots": [
            {
                "start_time": r["slot_start"],
                "available": max(0, cap - r["used"]),
                "capacity": cap,
            }
            for r in rows
        ],
    }
