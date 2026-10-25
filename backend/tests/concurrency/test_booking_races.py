import asyncio
import random
import uuid
from collections import Counter

from tests.integration.helpers import (
    at,
    book,
    create,
    fetchval,
    invariant_violations,  # noqa: F401
    make_user,
    new_key,
)


async def users(client, n: int):
    return await asyncio.gather(*(make_user(client) for _ in range(n)))


async def test_same_key_30_parallel_creates_one_booking(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    res = await create(client, admin)
    k = new_key()
    rs = await asyncio.gather(
        *(book(client, student, res["resource_id"], at(2, 9), at(2, 10), k=k) for _ in range(30))
    )
    assert {r.status_code for r in rs} == {201}
    assert len({r.json()["booking_id"] for r in rs}) == 1
    assert sum(r.headers.get("Idempotent-Replay") == "true" for r in rs) == 29
    assert await fetchval("SELECT count(*) FROM bookings WHERE user_id = $1", uuid.UUID(uid)) == 1
    assert await invariant_violations(res["resource_id"]) == 0


async def test_last_seat_20_users_one_winner(client):
    admin, _ = await make_user(client, "admin", "staff")
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    people = await users(client, 20)
    rs = await asyncio.gather(
        *(book(client, h, seat["resource_id"], at(2, 9), at(2, 10)) for h, _ in people)
    )
    assert Counter(r.status_code for r in rs) == {201: 1, 409: 19}
    rid = uuid.UUID(seat["resource_id"])
    assert (
        await fetchval(
            "SELECT count(*) FROM bookings WHERE resource_id = $1 AND status = 'CONFIRMED'",
            rid,
        )
        == 1
    )
    assert await invariant_violations(rid) == 0


async def test_room_capacity_is_never_exceeded(client):
    admin, _ = await make_user(client, "admin", "staff")
    room = await create(client, admin, capacity=5, max_quantity_per_booking=1)
    people = await users(client, 15)
    rs = await asyncio.gather(
        *(book(client, h, room["resource_id"], at(2, 9), at(2, 10)) for h, _ in people)
    )
    assert Counter(r.status_code for r in rs) == {201: 5, 409: 10}
    assert await invariant_violations(room["resource_id"]) == 0


async def test_one_user_parallel_requests_respect_the_limit(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    room = await create(client, admin, capacity=10)  # default limit: 2 active per resource
    rs = await asyncio.gather(
        *(book(client, student, room["resource_id"], at(2, 9 + i), at(2, 10 + i)) for i in range(6))
    )
    assert Counter(r.status_code for r in rs) == {201: 2, 409: 4}
    assert {r.json()["error"]["code"] for r in rs if r.status_code == 409} == {"USER_LIMIT_REACHED"}


async def test_overlapping_multi_slot_requests_never_oversubscribe(client):
    admin, _ = await make_user(client, "admin", "staff")
    room = await create(client, admin, capacity=5, max_quantity_per_booking=2)
    people = await users(client, 20)
    rng = random.Random(7)
    reqs = []
    for h, _ in people:
        start, length = rng.randrange(6), rng.randint(1, 3)
        reqs.append(
            book(
                client,
                h,
                room["resource_id"],
                at(2, 9 + start),
                at(2, 9 + start + length),
                q=rng.randint(1, 2),
            )
        )
    rs = await asyncio.gather(*reqs)
    codes = Counter(r.status_code for r in rs)
    assert set(codes) <= {
        201,
        409,
    }, f"unexpected statuses (503 would mean a deadlock): {codes}"
    assert codes[201] and codes[409], "test did not create real contention"
    assert await invariant_violations(room["resource_id"]) == 0
