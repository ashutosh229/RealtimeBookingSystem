import asyncio
import json
import uuid
from collections import Counter

import pytest

from app.messaging.consumer import BadMessage, process
from app.messaging.relay import envelope
from app.platform import db
from app.worker import handlers
from tests.integration.helpers import (
    at,
    book,
    create,
    fetch,
    fetchval,
    invariant_violations,
    make_user,
)
from tests.integration.test_promotion import cancel, status


async def body_of(booking_id: str, event_type: str) -> bytes:
    (row,) = await fetch(
        "SELECT id, event_id, aggregate_type, aggregate_id, event_type, schema_version, payload, created_at"
        " FROM outbox_events WHERE aggregate_id = $1 AND event_type = $2",
        uuid.UUID(booking_id),
        event_type,
    )
    return json.dumps(envelope(row)).encode()


async def seat(client, admin):
    return await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)


async def test_notify_creates_one_inbox_row_and_ignores_duplicates(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    s = await seat(client, admin)
    bid = (await book(client, student, s["resource_id"], at(2, 9), at(2, 10))).json()["booking_id"]
    body = await body_of(bid, "BookingConfirmed")
    pool = db.get_pool()
    assert await process(pool, "notify", body, handlers.notify) == "processed"
    assert await process(pool, "notify", body, handlers.notify) == "duplicate"
    rows = await fetch("SELECT type, payload FROM notifications WHERE user_id = $1", uuid.UUID(uid))
    assert [r["type"] for r in rows] == ["BookingConfirmed"]
    assert rows[0]["payload"]["status"] == "CONFIRMED" and rows[0]["payload"]["message"]
    assert (
        await fetchval(
            "SELECT count(*) FROM processed_events WHERE consumer = 'notify' AND event_id = $1",
            uuid.UUID(json.loads(body)["event_id"]),
        )
        == 1
    )


async def test_parallel_duplicate_deliveries_are_processed_once(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    s = await seat(client, admin)
    bid = (await book(client, student, s["resource_id"], at(2, 9), at(2, 10))).json()["booking_id"]
    body = await body_of(bid, "BookingConfirmed")
    pool = db.get_pool()
    results = await asyncio.gather(
        *(process(pool, "notify", body, handlers.notify) for _ in range(8))
    )
    assert Counter(results) == {"processed": 1, "duplicate": 7}
    assert (
        await fetchval("SELECT count(*) FROM notifications WHERE user_id = $1", uuid.UUID(uid)) == 1
    )


async def test_a_failing_handler_leaves_no_dedupe_row_so_a_retry_succeeds(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    s = await seat(client, admin)
    bid = (await book(client, student, s["resource_id"], at(2, 9), at(2, 10))).json()["booking_id"]
    body = await body_of(bid, "BookingConfirmed")
    eid = uuid.UUID(json.loads(body)["event_id"])

    async def boom(conn, event):
        await handlers.notify(conn, event)  # wrote its row ...
        raise RuntimeError("crash before commit")  # ... but the whole transaction must roll back

    with pytest.raises(RuntimeError):
        await process(db.get_pool(), "notify", body, boom)
    assert await fetchval("SELECT count(*) FROM processed_events WHERE event_id = $1", eid) == 0
    assert (
        await fetchval("SELECT count(*) FROM notifications WHERE user_id = $1", uuid.UUID(uid)) == 0
    )
    assert await process(db.get_pool(), "notify", body, handlers.notify) == "processed"
    assert (
        await fetchval("SELECT count(*) FROM notifications WHERE user_id = $1", uuid.UUID(uid)) == 1
    )


async def test_bad_messages_are_rejected_without_side_effects(client):
    pool = db.get_pool()
    for body in (b"not json", b"{}", json.dumps({"event_type": "Nope"}).encode()):
        with pytest.raises(BadMessage):
            await process(pool, "notify", body, handlers.notify)


async def test_capacity_released_event_promotes_the_waiter_exactly_once(client):
    admin, _ = await make_user(client, "admin", "staff")
    owner, _ = await make_user(client)
    waiter, w_id = await make_user(client)
    s = await seat(client, admin)
    rid = uuid.UUID(s["resource_id"])
    held = (await book(client, owner, s["resource_id"], at(2, 9), at(2, 10))).json()
    wl = (await book(client, waiter, s["resource_id"], at(2, 9), at(2, 10), waitlist=True)).json()
    await cancel(client, owner, held["booking_id"])
    assert await status(wl["booking_id"]) == "WAITLISTED"  # nothing promoted it yet

    body = await body_of(held["booking_id"], "CapacityReleased")
    pool = db.get_pool()
    assert await process(pool, "promote", body, handlers.promote) == "processed"
    assert await status(wl["booking_id"]) == "CONFIRMED"
    assert await process(pool, "promote", body, handlers.promote) == "duplicate"
    assert (
        await fetchval(
            "SELECT count(*) FROM allocation_records WHERE booking_id = $1"
            " AND decision_type = 'PROMOTE'",
            uuid.UUID(wl["booking_id"]),
        )
        == 1
    )

    promoted = await body_of(wl["booking_id"], "BookingPromoted")
    assert await process(pool, "notify", promoted, handlers.notify) == "processed"
    row = await fetchval("SELECT type FROM notifications WHERE user_id = $1", uuid.UUID(w_id))
    assert row == "BookingPromoted"
    assert await invariant_violations(rid) == 0
