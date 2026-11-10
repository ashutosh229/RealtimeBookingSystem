import asyncio
import uuid
from collections import Counter

from tests.integration.helpers import (
    at,
    book,
    create,
    fetch,
    fetchval,
    make_user,
    new_key,
)


async def test_every_competing_request_leaves_exactly_one_record(client):
    admin, _ = await make_user(client, "admin", "staff")
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    people = await asyncio.gather(*(make_user(client) for _ in range(20)))
    rs = await asyncio.gather(
        *(book(client, h, seat["resource_id"], at(2, 9), at(2, 10)) for h, _ in people)
    )
    assert Counter(r.status_code for r in rs) == {201: 1, 409: 19}
    rows = await fetch(
        "SELECT outcome, reason, count(*) AS n FROM booking_attempts WHERE resource_id = $1 GROUP BY 1, 2",
        uuid.UUID(seat["resource_id"]),
    )
    assert {(r["outcome"], r["reason"]): r["n"] for r in rows} == {
        ("CONFIRMED", None): 1,
        ("REJECTED", "CAPACITY_UNAVAILABLE"): 19,
    }


async def test_a_retry_storm_is_one_attempt(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    room = await create(client, admin)
    k = new_key()
    rs = await asyncio.gather(
        *(book(client, student, room["resource_id"], at(2, 9), at(2, 10), k=k) for _ in range(30))
    )
    assert {r.status_code for r in rs} == {201}
    assert (
        await fetchval("SELECT count(*) FROM booking_attempts WHERE user_id = $1", uuid.UUID(uid))
        == 1
    )
