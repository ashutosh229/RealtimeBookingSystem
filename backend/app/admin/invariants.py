"""Continuous evidence for the capacity and waitlist invariants (LLD sections 31.3 and 32).

Read-only SQL, safe to run against the live database at any time:

  I1  slot_usage.used equals the units held by CONFIRMED/COMPLETED bookings in every slot, and
      never exceeds capacity. Checked both ways, so a booking with no ledger row is caught too.
  I4  a WAITLISTED booking has exactly one ACTIVE waitlist entry, and vice versa.

    python -m app.admin.invariants            # last INVARIANT_LOOKBACK_DAYS days
    python -m app.admin.invariants --all      # the whole ledger (slower on a big database)

Exit status is 1 when a violation is found, so it can end a load test or a CI job.
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta

import asyncpg

from app.platform import clock
from app.platform.config import get_settings

log = logging.getLogger("rtbs.invariants")

LEDGER_SQL = """
WITH expected AS (
  SELECT b.resource_id, g.slot_start, SUM(b.quantity)::int AS q
  FROM bookings b
  JOIN resources r ON r.resource_id = b.resource_id
  CROSS JOIN LATERAL generate_series(
      b.start_time,
      b.end_time - make_interval(mins => r.slot_minutes),
      make_interval(mins => r.slot_minutes)) AS g(slot_start)
  WHERE b.status IN ('CONFIRMED', 'COMPLETED')
    AND ($1::timestamptz IS NULL OR g.slot_start >= $1)
  GROUP BY b.resource_id, g.slot_start
), actual AS (
  SELECT resource_id, slot_start, used, capacity FROM slot_usage
  WHERE $1::timestamptz IS NULL OR slot_start >= $1
)
SELECT COALESCE(a.resource_id, e.resource_id) AS resource_id,
       COALESCE(a.slot_start, e.slot_start) AS slot_start,
       COALESCE(a.used, 0) AS used,
       COALESCE(e.q, 0) AS expected,
       a.capacity,
       count(*) OVER () AS total
FROM actual a
FULL JOIN expected e ON e.resource_id = a.resource_id AND e.slot_start = a.slot_start
WHERE COALESCE(a.used, 0) <> COALESCE(e.q, 0)
   OR COALESCE(a.used, 0) > COALESCE(a.capacity, 2147483647)
ORDER BY 2
LIMIT $2
"""

WAITLIST_SQL = """
SELECT * FROM (
  SELECT 'waitlisted_booking_without_active_entry' AS kind, b.booking_id::text AS ref
  FROM bookings b
  WHERE b.status = 'WAITLISTED'
    AND NOT EXISTS (SELECT 1 FROM waitlist_entries w
                    WHERE w.booking_id = b.booking_id AND w.status = 'ACTIVE')
  UNION ALL
  SELECT 'active_entry_without_waitlisted_booking', w.waitlist_id::text
  FROM waitlist_entries w JOIN bookings b ON b.booking_id = w.booking_id
  WHERE w.status = 'ACTIVE' AND b.status <> 'WAITLISTED'
) v
LIMIT $1
"""


async def check(
    conn: asyncpg.Connection, *, since: datetime | None = None, limit: int = 20
) -> dict:
    """since=None checks everything. Returns counts and up to `limit` examples of each kind."""
    ledger = await conn.fetch(LEDGER_SQL, since, limit)
    waitlist = await conn.fetch(WAITLIST_SQL, limit)
    return {
        "ok": not ledger and not waitlist,
        "checked_at": clock.now().isoformat(),
        "since": since.isoformat() if since else None,
        "ledger_violations": ledger[0]["total"] if ledger else 0,
        "waitlist_violations": len(waitlist),
        "ledger_examples": [
            {
                "resource_id": str(r["resource_id"]),
                "slot_start": r["slot_start"].isoformat(),
                "used": r["used"],
                "expected": r["expected"],
                "capacity": r["capacity"],
            }
            for r in ledger
        ],
        "waitlist_examples": [{"kind": r["kind"], "ref": r["ref"]} for r in waitlist],
    }


def lookback_start() -> datetime | None:
    days = get_settings().invariant_lookback_days
    return clock.now() - timedelta(days=days) if days > 0 else None


async def run_and_log(conn: asyncpg.Connection) -> dict:
    """The worker's periodic check. A violation is logged at ERROR with examples."""
    result = await check(conn, since=lookback_start())
    if result["ok"]:
        log.info("invariants ok (window since %s)", result["since"] or "the beginning")
    else:
        log.error("INVARIANT VIOLATION: %s", json.dumps(result, default=str))
    return result


async def _main(everything: bool) -> int:
    from app.platform import db

    await db.init_pool()
    try:
        async with db.get_pool().acquire() as conn:
            result = await check(conn, since=None if everything else lookback_start())
    finally:
        await db.close_pool()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="check the whole ledger, not just recent")
    raise SystemExit(asyncio.run(_main(ap.parse_args().all)))
