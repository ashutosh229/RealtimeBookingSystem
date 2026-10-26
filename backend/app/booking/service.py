import asyncio
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, timedelta
from uuid import UUID

import asyncpg

from app.booking import idempotency as idem
from app.booking import ledger, repo
from app.booking.schemas import BookingCreate, BookingOut
from app.booking.state_machine import (
    TERMINAL,
    BookingStatus,
    CapacityEffect,
    capacity_effect,
    check_transition,
)
from app.messaging import events, outbox
from app.platform import clock
from app.platform.errors import ApiError
from app.resources import repo as resources_repo
from app.resources.policy import policy_for
from app.resources.slots import booking_slots

POLICY_VERSION = "1.0"
MAX_ATTEMPTS = 3


@dataclass
class Result:
    status: int
    body: dict
    replayed: bool = False


def request_hash(cmd: BookingCreate) -> str:
    """Canonical fingerprint: the same instant in different UTC offsets hashes identically."""
    canon = {
        "r": str(cmd.resource_id),
        "s": cmd.start_time.astimezone(UTC).isoformat(),
        "e": cmd.end_time.astimezone(UTC).isoformat(),
        "q": cmd.quantity,
        "w": cmd.waitlist_if_full,
    }
    return hashlib.sha256(json.dumps(canon, sort_keys=True).encode()).hexdigest()


async def create_booking(
    conn: asyncpg.Connection, user: dict, cmd: BookingCreate, key: str
) -> Result:
    h = request_hash(cmd)
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await _create_once(conn, user, cmd, key, h)
        except asyncpg.DeadlockDetectedError:
            await asyncio.sleep(random.uniform(0, 0.02 * (attempt + 1)))
        except (
            asyncpg.ExclusionViolationError
        ):  # Class A backstop: the ledger should have refused first
            raise ApiError(
                409, "CAPACITY_UNAVAILABLE", "No capacity for the requested time"
            ) from None
    raise ApiError(
        503,
        "SERVICE_BUSY",
        "Busy, retry with the same Idempotency-Key",
        headers={"Retry-After": "1"},
    )


async def _create_once(
    conn: asyncpg.Connection, user: dict, cmd: BookingCreate, key: str, h: str
) -> Result:
    uid: UUID = user["user_id"]
    async with conn.transaction():  # everything below commits or rolls back together
        if not await idem.try_claim(conn, uid, key, h):
            code, body = await idem.replay(conn, uid, key, h)
            return Result(code, body, replayed=True)

        res = await resources_repo.get_for_share(conn, cmd.resource_id)
        if res is None:
            raise ApiError(404, "NOT_FOUND", "Resource not found")
        if not res["active"]:
            raise ApiError(409, "RESOURCE_INACTIVE", "Resource is not accepting bookings")

        policy, now = policy_for(res["type"]), clock.now()
        slots = policy.validate_interval(res, cmd.start_time, cmd.end_time, now)
        policy.check_eligibility(res, user)
        qty = policy.required_quantity(res, cmd.quantity)

        # Serialise this user's bookings so the limit check cannot be raced by parallel requests.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"booking-user:{uid}")
        if (
            await repo.count_active(conn, uid, res["resource_id"], now)
            >= res["max_active_per_user"]
        ):
            raise ApiError(
                409,
                "USER_LIMIT_REACHED",
                f"At most {res['max_active_per_user']} active bookings per resource",
            )

        got = await ledger.acquire(conn, res["resource_id"], slots, qty, res["capacity"])
        if not got and not cmd.waitlist_if_full:
            body = {
                "error": {
                    "code": "CAPACITY_UNAVAILABLE",
                    "message": "No capacity for the requested time",
                    "details": {},
                }
            }
            await idem.complete(conn, uid, key, 409, body, None)
            return Result(409, body)

        status = BookingStatus.CONFIRMED if got else BookingStatus.WAITLISTED
        check_transition(BookingStatus.REQUESTED, status)
        row = await repo.insert_booking(
            conn,
            user_id=uid,
            resource_id=res["resource_id"],
            start=cmd.start_time,
            end=cmd.end_time,
            quantity=qty,
            status=status.value,
            exclusive=policy.is_exclusive,
            key=key,
            req_hash=h,
            confirmed_at=now if got else None,
        )
        bid = row["booking_id"]
        await repo.add_history(
            conn, bid, BookingStatus.REQUESTED.value, status.value, uid, "created"
        )

        wl, position = None, None
        if got:
            await repo.add_allocation(
                conn,
                bid,
                res["policy_name"],
                POLICY_VERSION,
                "ADMIT",
                {"reason": "capacity_available"},
            )
            event_cls = events.BookingConfirmed
        else:
            wl = await repo.add_waitlist(
                conn,
                booking_id=bid,
                user_id=uid,
                resource_id=res["resource_id"],
                start=cmd.start_time,
                end=cmd.end_time,
                quantity=qty,
            )
            position = await repo.waitlist_position(
                conn, res["resource_id"], wl["seq"], cmd.start_time, cmd.end_time
            )
            await repo.add_allocation(
                conn,
                bid,
                res["policy_name"],
                POLICY_VERSION,
                "REJECT_FULL",
                {"reason": "capacity_unavailable", "waitlist_seq": wl["seq"]},
            )
            event_cls = events.BookingWaitlisted

        await outbox.add(
            conn,
            event_cls(
                aggregate_id=bid,
                occurred_at=now,
                payload=events.BookingPayload(
                    booking_id=bid,
                    user_id=uid,
                    resource_id=res["resource_id"],
                    start_time=cmd.start_time,
                    end_time=cmd.end_time,
                    quantity=qty,
                    status=status.value,
                ),
            ),
        )

        body = BookingOut(
            booking_id=bid,
            status=status.value,
            resource_id=res["resource_id"],
            start_time=cmd.start_time,
            end_time=cmd.end_time,
            quantity=qty,
            waitlist_position=position,
            waitlist_id=wl["waitlist_id"] if wl else None,
            expires_at=cmd.start_time if wl else None,
            created_at=row["created_at"],
        ).model_dump(mode="json")
        code = 201 if got else 202
        await idem.complete(conn, uid, key, code, body, bid)
        return Result(code, body)


def check_cancellable(b, role: str, now) -> None:
    """Cancellation policy (pure). Waitlist entries can always be withdrawn."""
    closed = ApiError(409, "CANCELLATION_WINDOW_CLOSED", "This booking can no longer be cancelled")
    if b["status"] == "WAITLISTED":
        return
    if role == "admin":
        if b["end_time"] <= now:
            raise closed
        return
    if b["start_time"] - timedelta(minutes=b["min_cancel_notice_minutes"]) <= now:
        raise closed


async def cancel_locked(
    conn, b, actor_id: UUID, reason: str, now, emit_release: bool = True
) -> None:
    """Cancel one booking whose row is already locked (FOR UPDATE). Call inside a transaction."""
    src = BookingStatus(b["status"])
    effect = capacity_effect(
        src, BookingStatus.CANCELLED
    )  # raises IllegalTransition for bad states
    bid = b["booking_id"]
    if effect == CapacityEffect.RELEASE:
        slots = booking_slots(b["start_time"], b["end_time"], b["slot_minutes"])
        await ledger.release(conn, b["resource_id"], slots, b["quantity"])
    else:
        await repo.cancel_waitlist_entry(conn, bid)
    await repo.mark_cancelled(conn, bid, now)
    await repo.add_history(conn, bid, src.value, BookingStatus.CANCELLED.value, actor_id, reason)
    await outbox.add(
        conn,
        events.BookingCancelled(
            aggregate_id=bid,
            occurred_at=now,
            payload=events.BookingPayload(
                booking_id=bid,
                user_id=b["user_id"],
                resource_id=b["resource_id"],
                start_time=b["start_time"],
                end_time=b["end_time"],
                quantity=b["quantity"],
                status=BookingStatus.CANCELLED.value,
            ),
        ),
    )
    if effect == CapacityEffect.RELEASE and emit_release:
        await outbox.add(
            conn,
            events.CapacityReleased(
                aggregate_id=bid,
                occurred_at=now,
                payload=events.CapacityReleasedPayload(
                    resource_id=b["resource_id"],
                    booking_id=bid,
                    start_time=b["start_time"],
                    end_time=b["end_time"],
                    quantity=b["quantity"],
                ),
            ),
        )


async def cancel_booking(conn, actor: dict, booking_id: UUID):
    now = clock.now()
    async with conn.transaction():
        b = await repo.get_for_update(conn, booking_id)
        if b is None or (b["user_id"] != actor["user_id"] and actor["role"] != "admin"):
            raise ApiError(
                404, "NOT_FOUND", "Booking not found"
            )  # not 403: do not reveal existence
        if BookingStatus(b["status"]) not in TERMINAL:  # already terminal: return it unchanged
            check_cancellable(b, actor["role"], now)
            reason = "user_cancel" if b["user_id"] == actor["user_id"] else "admin_cancel"
            await cancel_locked(conn, b, actor["user_id"], reason, now)
    return await repo.get_view(conn, booking_id)


async def get_booking(conn, user: dict, booking_id: UUID) -> dict:
    row = await repo.get_view(conn, booking_id)
    if row is None or (row["user_id"] != user["user_id"] and user["role"] != "admin"):
        raise ApiError(404, "NOT_FOUND", "Booking not found")
    return {
        **dict(row),
        "history": [dict(h) for h in await repo.history(conn, booking_id)],
    }


async def force_deactivate(conn, admin: dict, resource_id: UUID):
    """Deactivate a resource and cancel its future bookings atomically.
    The FOR UPDATE lock waits for in-flight creates (they hold FOR SHARE) and blocks new ones.
    """
    now = clock.now()
    async with conn.transaction():
        if await resources_repo.get_for_update(conn, resource_id) is None:
            raise ApiError(404, "NOT_FOUND", "Resource not found")
        for b in await repo.active_for_resource_for_update(conn, resource_id, now):
            await cancel_locked(
                conn,
                b,
                admin["user_id"],
                "resource_deactivated",
                now,
                emit_release=False,
            )
        await conn.execute(
            "UPDATE resources SET active = false, version = version + 1 WHERE resource_id = $1",
            resource_id,
        )
    return await resources_repo.get(conn, resource_id)


async def promote_locked(
    conn, res, row, now, policy_name: str, policy_version: str, inputs: dict
) -> bool:
    """Confirm one WAITLISTED booking whose row the caller already holds FOR UPDATE.
    Returns False (changing nothing) when the ledger cannot absorb it."""
    bid = row["booking_id"]
    slots = booking_slots(row["start_time"], row["end_time"], res["slot_minutes"])
    async with conn.transaction():  # savepoint: a failure leaves no partial change
        if not await ledger.acquire(
            conn, res["resource_id"], slots, row["quantity"], res["capacity"]
        ):
            return False
        check_transition(BookingStatus.WAITLISTED, BookingStatus.CONFIRMED)
        await repo.mark_promoted(conn, bid, now)
        await repo.add_history(conn, bid, "WAITLISTED", "CONFIRMED", None, "promoted")
        await repo.add_allocation(conn, bid, policy_name, policy_version, "PROMOTE", inputs)
        await outbox.add(
            conn,
            events.BookingPromoted(
                aggregate_id=bid,
                occurred_at=now,
                payload=events.BookingPayload(
                    booking_id=bid,
                    user_id=row["user_id"],
                    resource_id=res["resource_id"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    quantity=row["quantity"],
                    status=BookingStatus.CONFIRMED.value,
                ),
            ),
        )
    return True
