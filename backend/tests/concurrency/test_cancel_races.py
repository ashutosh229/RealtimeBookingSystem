import asyncio
import random
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


async def users(client, n):
    return await asyncio.gather(*(make_user(client) for _ in range(n)))


async def cancel(c, headers, bid):
    return await c.post(f"/v1/bookings/{bid}/cancel", headers=headers)


async def total_used(rid):
    return await fetchval(
        "SELECT COALESCE(SUM(used), 0) FROM slot_usage WHERE resource_id = $1", rid
    )


async def test_parallel_cancels_of_one_booking_release_exactly_once(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = uuid.UUID(seat["resource_id"])
    bid = (await book(client, a, rid, at(2, 9), at(2, 10))).json()["booking_id"]
    rs = await asyncio.gather(*(cancel(client, a, bid) for _ in range(20)))
    assert {r.status_code for r in rs} == {200}  # a double release would raise a 500
    assert await total_used(rid) == 0
    assert (
        await fetchval(
            "SELECT count(*) FROM outbox_events WHERE aggregate_id = $1 AND event_type = 'CapacityReleased'",
            uuid.UUID(bid),
        )
        == 1
    )
    assert await invariant_violations(rid) == 0


async def test_cancel_racing_new_bookings_on_the_last_seat(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = uuid.UUID(seat["resource_id"])
    bid = (await book(client, a, rid, at(2, 9), at(2, 10))).json()["booking_id"]
    others = await users(client, 10)
    out = await asyncio.gather(
        cancel(client, a, bid),
        *(book(client, h, rid, at(2, 9), at(2, 10)) for h, _ in others),
    )
    assert out[0].status_code == 200
    assert {r.status_code for r in out[1:]} <= {201, 409}
    assert (
        await fetchval(
            "SELECT count(*) FROM bookings WHERE resource_id = $1 AND status = 'CONFIRMED'",
            rid,
        )
        <= 1
    )
    assert await invariant_violations(rid) == 0


async def test_parallel_cancels_on_shared_slots_do_not_deadlock(client):
    admin, _ = await make_user(client, "admin", "staff")
    room = await create(client, admin, capacity=20, max_quantity_per_booking=1)
    rid = uuid.UUID(room["resource_id"])
    people = await users(client, 12)
    rng = random.Random(3)
    made = await asyncio.gather(
        *(
            book(
                client,
                h,
                rid,
                at(2, 9 + (s := rng.randrange(3))),
                at(2, 9 + s + rng.randint(1, 3)),
            )
            for h, _ in people
        )
    )
    assert {r.status_code for r in made} == {201}
    rs = await asyncio.gather(
        *(cancel(client, h, r.json()["booking_id"]) for (h, _), r in zip(people, made, strict=True))
    )
    assert Counter(r.status_code for r in rs) == {200: 12}  # a 500 or 503 here would be a deadlock
    assert await total_used(rid) == 0
    assert await invariant_violations(rid) == 0


async def test_force_deactivate_racing_concurrent_creates(client):
    admin, _ = await make_user(client, "admin", "staff")
    room = await create(client, admin, capacity=50, max_quantity_per_booking=1)
    rid = uuid.UUID(room["resource_id"])
    people = await users(client, 15)
    out = await asyncio.gather(
        client.post(f"/v1/admin/resources/{rid}/deactivate", json={"force": True}, headers=admin),
        *(book(client, h, rid, at(2, 9), at(2, 10)) for h, _ in people),
    )
    assert out[0].status_code == 200
    codes = Counter(r.status_code for r in out[1:])
    assert set(codes) <= {201, 409}, codes
    assert {r.json()["error"]["code"] for r in out[1:] if r.status_code == 409} <= {
        "RESOURCE_INACTIVE"
    }
    # whichever side won each race, nothing may be left active on a deactivated resource
    assert (
        await fetchval(
            "SELECT count(*) FROM bookings WHERE resource_id = $1"
            " AND status IN ('CONFIRMED','WAITLISTED')",
            rid,
        )
        == 0
    )
    assert await total_used(rid) == 0
    assert await invariant_violations(rid) == 0
