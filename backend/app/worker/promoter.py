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

    strict=False: backfilling (a request that does not fit is skipped, the next is tried).
    strict=True: head-of-line blocking (the first request that does not fit stops the pass).
    Candidates failing eligibility or the cooldown are recorded once as SKIP_INELIGIBLE and excluded.
    """
    now, promoted = clock.now(), []
    async with conn.transaction():
        if not await conn.fetchval(
            "SELECT pg_try_advisory_xact_lock(hashtext($1))", f"promote:{resource_id}"
        ):
            return []  # another promoter owns this resource right now
        res = await resources_repo.get_for_share(conn, resource_id)
        if res is None or not res["active"]:
            return []
        rows = await alloc_repo.lock_waiting(conn, resource_id, now)
        if not rows:
            return []

        policy = policy_by_name(res["policy_name"])
        settings = get_settings()
        window, k = settings.fair_share_window_days, settings.contention_min_waiting
        gap = timedelta(minutes=settings.promotion_min_gap_minutes)
        since = now - timedelta(days=window)
        user_ids = list({r["user_id"] for r in rows})
        recent = await alloc_repo.recent_counts(conn, user_ids, res["type"], since)
        contended = await alloc_repo.recent_contended_counts(conn, user_ids, res["type"], since, k)
        ages = await alloc_repo.win_ages(conn, user_ids, res["type"], since, now)
        cooling: set[UUID] = set()
        if gap:
            cooling = set(
                await alloc_repo.users_with_recent_win(conn, user_ids, res["type"], now - gap)
            )

        def make_ctx() -> AllocationContext:
            return AllocationContext(
                now=now,
                recent_allocations=dict(recent),
                window_days=window,
                recent_contended=dict(contended),
                win_ages={u: list(a) for u, a in ages.items()},
            )

        by_id = {r["booking_id"]: r for r in rows}
        ctx = make_ctx()
        pending: list[Candidate] = []
        for r in rows:
            cand = Candidate(
                id=r["booking_id"],
                user_id=r["user_id"],
                seq=r["seq"],
                created_at=r["created_at"],
                quantity=r["quantity"],
            )
            reason = _ineligible(res, r, now) or ("COOLDOWN" if r["user_id"] in cooling else None)
            if reason:
                await alloc_repo.add_skip_once(
                    conn,
                    cand.id,
                    policy.name,
                    policy.version,
                    policy.explain(cand, ctx),
                    reason,
                )
            else:
                pending.append(cand)

        halt = False
        while pending and not halt:
            ctx = make_ctx()
            winner, waiting_after = None, 0
            for cand in policy.rank(pending, ctx):
                waiting_after = len(pending) - 1  # others still queued if this one wins
                inputs = {**policy.explain(cand, ctx), "waiting_after": waiting_after}
                try:
                    ok = await booking_service.promote_locked(
                        conn,
                        res,
                        by_id[cand.id],
                        now,
                        policy.name,
                        policy.version,
                        inputs,
                    )
                except asyncpg.ExclusionViolationError:  # ledger and constraint disagree: a bug
                    log.error("exclusion violation while promoting %s", cand.id)
                    ok = False
                if ok:
                    winner = cand
                    break
                pending.remove(cand)  # capacity only shrinks during a pass
                if strict:
                    halt = True
                    break
            if winner is None:
                break
            promoted.append(winner.id)
            pending.remove(winner)
            recent[winner.user_id] = recent.get(winner.user_id, 0) + 1  # re-rank with new usage
            ages.setdefault(winner.user_id, []).append(0.0)
            if waiting_after >= k:
                contended[winner.user_id] = contended.get(winner.user_id, 0) + 1
            if gap:  # the winner now cools down: its other requests leave this pass
                cooling.add(winner.user_id)
                pending = [c for c in pending if c.user_id != winner.user_id]
    return promoted
