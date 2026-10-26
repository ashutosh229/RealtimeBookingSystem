"""Waitlist promotion (LLD section 23)."""

import logging
from datetime import timedelta
from uuid import UUID

import asyncpg

from app.allocation import repo as alloc_repo
from app.allocation.base import AllocationContext, Candidate
from app.allocation.registry import policy_by_name
from app.booking import service as booking_service
from app.platform import clock
from app.platform.config import get_settings
from app.platform.errors import ApiError
from app.resources import repo as resources_repo
from app.resources.policy import policy_for

log = logging.getLogger("rtbs.promoter")


def _ineligible(res, row, now) -> str | None:
    """Recheck at promotion time: rules may have changed since the request joined the queue (I5)."""
    if not row["is_active"]:
        return "USER_INACTIVE"
    rules = policy_for(res["type"])
    try:
        rules.check_eligibility(res, {"user_group": row["user_group"]})
        rules.validate_interval(res, row["start_time"], row["end_time"], now)
    except ApiError as e:
        return e.code
    return None


async def promote_for_resource(
    conn: asyncpg.Connection, resource_id: UUID, *, strict: bool = False
) -> list[UUID]:
    """Promote as many waitlisted bookings as the freed capacity allows. Returns promoted booking ids.

    strict=False: backfilling, so a request that does not fit is skipped and the next is tried.
    strict=True: head-of-line blocking, so the first request that does not fit stops the pass.
    Safe to call repeatedly and concurrently: a second caller finds capacity taken or the lock held.
    """
    now, promoted = clock.now(), []
    async with conn.transaction():
        if not await conn.fetchval(
            "SELECT pg_try_advisory_xact_lock(hashtext($1))", f"promote:{resource_id}"
        ):
            return []  # another promoter owns this resource right now
        res = await resources_repo.get_for_share(
            conn, resource_id
        )  # blocks admin capacity change / deactivation
        if res is None or not res["active"]:
            return []
        rows = await alloc_repo.lock_waiting(conn, resource_id, now)
        if not rows:
            return []

        policy = policy_by_name(res["policy_name"])
        window = get_settings().fair_share_window_days
        recent = await alloc_repo.recent_counts(
            conn,
            list({r["user_id"] for r in rows}),
            res["type"],
            now - timedelta(days=window),
        )
        by_id = {r["booking_id"]: r for r in rows}
        pending = [
            Candidate(
                id=r["booking_id"],
                user_id=r["user_id"],
                seq=r["seq"],
                created_at=r["created_at"],
                quantity=r["quantity"],
            )
            for r in rows
        ]

        halt = False
        while pending and not halt:
            ctx = AllocationContext(now=now, recent_allocations=dict(recent), window_days=window)
            winner = None
            for cand in policy.rank(pending, ctx):
                row = by_id[cand.id]
                reason = _ineligible(res, row, now)
                if reason:
                    await alloc_repo.add_skip_once(
                        conn,
                        cand.id,
                        policy.name,
                        policy.version,
                        policy.explain(cand, ctx),
                        reason,
                    )
                    pending.remove(cand)
                    continue
                try:
                    ok = await booking_service.promote_locked(
                        conn,
                        res,
                        row,
                        now,
                        policy.name,
                        policy.version,
                        policy.explain(cand, ctx),
                    )
                except (
                    asyncpg.ExclusionViolationError
                ):  # ledger and exclusion constraint disagree: a bug
                    log.error("exclusion violation while promoting %s", cand.id)
                    ok = False
                if ok:
                    winner = cand
                    break
                pending.remove(
                    cand
                )  # capacity only shrinks during a pass, so it will not fit later either
                if strict:
                    halt = True
                    break
            if winner is None:
                break
            promoted.append(winner.id)
            pending.remove(winner)
            recent[winner.user_id] = recent.get(winner.user_id, 0) + 1  # re-rank with the new usage
    return promoted
