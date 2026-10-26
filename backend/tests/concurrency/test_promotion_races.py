import asyncio
import uuid
from collections import Counter

from tests.integration.helpers import (
    at,
    book,
    create,
    fetchval,
    invariant_violations,
    make_user,
)
from tests.integration.test_promotion import cancel, promote


async def seat_with_waiters(client, n_waiters: int):
    admin, _ = await make_user(client, "admin", "staff")
    owner, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = seat["resource_id"]
    bk_o = (await book(client, owner, rid, at(2, 9), at(2, 10))).json()
    waiters = []
    for _ in range(n_waiters):
        h, _ = await make_user(client)
        waiters.append(
            (
                h,
                (await book(client, h, rid, at(2, 9), at(2, 10), waitlist=True)).json()[
                    "booking_id"
                ],
            )
        )
    await cancel(client, owner, bk_o["booking_id"])
    return rid, waiters


async def test_parallel_promoters_promote_exactly_once(client):
    rid, _ = await seat_with_waiters(client, 5)
    results = await asyncio.gather(*(promote(rid) for _ in range(6)))
    promoted = [i for r in results for i in r]
    assert len(promoted) == 1
    assert (
        await fetchval(
            "SELECT count(*) FROM bookings WHERE resource_id = $1 AND status = 'CONFIRMED'",
            uuid.UUID(rid),
        )
        == 1
    )
    assert (
        await fetchval(
            "SELECT count(*) FROM outbox_events WHERE event_type = 'BookingPromoted'"
            " AND aggregate_id = $1",
            promoted[0],
        )
        == 1
    )
    assert await invariant_violations(rid) == 0


async def test_promotion_racing_cancellation_of_the_waiters(client):
    rid, waiters = await seat_with_waiters(client, 5)
    out = await asyncio.gather(
        promote(rid),
        promote(rid),
        *(cancel(client, h, bid) for h, bid in waiters),
    )
    assert Counter(r.status_code for r in out[2:]) == {
        200: 5
    }  # a 500 here would be a deadlock or bad release
    assert (
        await fetchval(
            "SELECT count(*) FROM bookings WHERE resource_id = $1 AND status = 'CONFIRMED'",
            uuid.UUID(rid),
        )
        == 0
    )  # everyone cancelled, including any promoted
    assert (
        await fetchval(
            "SELECT COALESCE(SUM(used), 0) FROM slot_usage WHERE resource_id = $1",
            uuid.UUID(rid),
        )
        == 0
    )
    assert await invariant_violations(rid) == 0
