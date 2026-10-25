import asyncio
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC
from uuid import UUID

import asyncpg

from app.booking import idempotency as idem
from app.booking import ledger, repo
from app.booking.schemas import BookingCreate, BookingOut
from app.booking.state_machine import BookingStatus, check_transition
from app.messaging import events, outbox
from app.platform import clock
from app.platform.errors import ApiError
from app.resources import repo as resources_repo
from app.resources.policy import policy_for

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
