"""Periodic housekeeping. Safe to run from several workers: one advisory lock admits one at a time."""

import logging
from uuid import UUID

import asyncpg

from app.booking import service as booking_service
from app.platform import clock
from app.worker import promoter

log = logging.getLogger("rtbs.sweeper")
SWEEPER_LOCK = "rtbs-sweeper"


async def promote_sweep(conn: asyncpg.Connection, now, resource_ids: list[UUID] | None) -> int:
    rows = await conn.fetch(
        "SELECT DISTINCT resource_id FROM waitlist_entries WHERE status = 'ACTIVE' AND expires_at > $1"
        " AND ($2::uuid[] IS NULL OR resource_id = ANY($2))",
        now,
        resource_ids,
    )
    promoted = 0
    for r in rows:
        try:
            promoted += len(await promoter.promote_for_resource(conn, r["resource_id"]))
        except Exception:  # one bad resource must not stop the others
            log.exception("promotion failed for resource %s", r["resource_id"])
    return promoted


async def purge(conn: asyncpg.Connection) -> int:
    """Uses database time on purpose: old rows are old regardless of the app clock."""
    a = await conn.execute(
        "DELETE FROM idempotency_keys WHERE created_at < now() - interval '24 hours'"
    )
    b = await conn.execute("DELETE FROM refresh_tokens WHERE expires_at < now() - interval '1 day'")
    return int(a.split()[-1]) + int(b.split()[-1])


async def run_cycle(conn: asyncpg.Connection, resource_ids: list[UUID] | None = None) -> dict:
    """Order matters: expire first, so an expired request is never promoted."""
    now = clock.now()
    expired = await booking_service.expire_waitlisted(conn, now, resource_ids)
    promoted = await promote_sweep(conn, now, resource_ids)
    completed = await booking_service.complete_finished(conn, now, resource_ids)
    return {
        "expired": expired,
        "promoted": promoted,
        "completed": completed,
        "purged": await purge(conn),
    }


async def run_locked(
    conn: asyncpg.Connection, resource_ids: list[UUID] | None = None
) -> dict | None:
    """None means another sweeper is active right now."""
    if not await conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", SWEEPER_LOCK):
        return None
    try:
        return await run_cycle(conn, resource_ids)
    finally:
        await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", SWEEPER_LOCK)
