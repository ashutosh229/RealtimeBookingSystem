import asyncio
import json
import os
import uuid

import aio_pika
import pytest
import pytest_asyncio

from app.messaging import consumer, relay, topology
from app.messaging.relay import envelope
from app.platform import db
from app.worker import handlers
from tests.integration.helpers import at, book, create, fetch, fetchval, make_user

AMQP = os.environ.get("TEST_AMQP_URL") or os.environ.get(
    "AMQP_URL", "amqp://guest:guest@localhost:5672/"
)


@pytest_asyncio.fixture
async def broker():
    try:
        conn = await aio_pika.connect_robust(AMQP, timeout=3)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"RabbitMQ not reachable: {e}")
    channel = await conn.channel()
    topo = topology.Topology(prefix=f"t{uuid.uuid4().hex[:8]}.", delays_ms=(100, 100))
    declared = await topology.declare(channel, topo)
    yield channel, topo, declared
    for q in topo.all_queues():
        await channel.queue_delete(q)
    await declared.exchange.delete()
    await conn.close()


async def eventually(fn, timeout: float = 10.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while True:
        value = await fn()
        if value:
            return value
        if loop.time() > end:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.1)


async def make_booking(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    s = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    bid = (await book(client, student, s["resource_id"], at(2, 9), at(2, 10))).json()["booking_id"]
    row = (
        await fetch(
            "SELECT id, event_id, aggregate_type, aggregate_id, event_type, schema_version, payload, created_at"
            " FROM outbox_events WHERE aggregate_id = $1 AND event_type = 'BookingConfirmed'",
            uuid.UUID(bid),
        )
    )[0]
    return uuid.UUID(uid), row


def start(stop, topo, handler, **kw):
    return asyncio.create_task(
        consumer.run_consumers(stop, handlers={"notify": handler}, topo=topo, amqp_url=AMQP, **kw)
    )


async def inbox(uid):
    return await fetchval("SELECT count(*) FROM notifications WHERE user_id = $1", uid)


async def dlq_count(channel, topo) -> int:
    q = await channel.declare_queue(topo.dlq("notify"), durable=True, passive=True)
    return q.declaration_result.message_count


async def test_committed_event_reaches_the_inbox_through_the_broker(client, broker):
    channel, topo, declared = broker
    uid, row = await make_booking(client)
    stop = asyncio.Event()
    task = start(stop, topo, handlers.notify)
    async with db.get_pool().acquire() as c:
        assert await relay.relay_once(c, declared.exchange, only=[row["event_id"]]) == 1
        assert (
            await relay.relay_once(c, declared.exchange, only=[row["event_id"]]) == 0
        )  # marked published
    assert await fetchval(
        "SELECT published_at IS NOT NULL FROM outbox_events WHERE id = $1", row["id"]
    )
    await eventually(lambda: inbox(uid))
    stop.set()
    await task


async def test_duplicate_deliveries_create_one_notification(client, broker):
    channel, topo, declared = broker
    uid, row = await make_booking(client)
    body = json.dumps(envelope(row)).encode()
    stop = asyncio.Event()
    task = start(stop, topo, handlers.notify)
    for _ in range(3):
        await declared.exchange.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key="booking.confirmed",
        )
    await eventually(lambda: inbox(uid))
    await asyncio.sleep(0.5)
    assert await inbox(uid) == 1
    assert (
        await fetchval("SELECT count(*) FROM processed_events WHERE event_id = $1", row["event_id"])
        == 1
    )
    stop.set()
    await task


async def test_a_transient_failure_is_retried_until_it_succeeds(client, broker):
    channel, topo, declared = broker
    uid, row = await make_booking(client)
    calls = []

    async def flaky(conn, event):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("temporary")
        await handlers.notify(conn, event)

    stop = asyncio.Event()
    task = start(stop, topo, flaky, max_attempts=5)
    await declared.exchange.publish(
        aio_pika.Message(
            body=json.dumps(envelope(row)).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="booking.confirmed",
    )
    await eventually(lambda: inbox(uid))
    assert len(calls) == 3 and await inbox(uid) == 1 and await dlq_count(channel, topo) == 0
    stop.set()
    await task


async def test_a_permanent_failure_ends_in_the_dead_letter_queue(client, broker):
    channel, topo, declared = broker
    uid, row = await make_booking(client)

    async def always(conn, event):
        raise RuntimeError("permanent")

    stop = asyncio.Event()
    task = start(stop, topo, always, max_attempts=3)
    await declared.exchange.publish(
        aio_pika.Message(
            body=json.dumps(envelope(row)).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="booking.confirmed",
    )

    async def landed():
        return await dlq_count(channel, topo) == 1

    await eventually(landed)
    assert await inbox(uid) == 0
    assert (
        await fetchval("SELECT count(*) FROM processed_events WHERE event_id = $1", row["event_id"])
        == 0
    )
    stop.set()
    await task


async def test_garbage_goes_straight_to_the_dead_letter_queue(client, broker):
    channel, topo, declared = broker
    stop = asyncio.Event()
    task = start(stop, topo, handlers.notify)
    await declared.exchange.publish(
        aio_pika.Message(body=b"garbage"), routing_key="booking.confirmed"
    )

    async def landed():
        return await dlq_count(channel, topo) == 1

    await eventually(landed)
    stop.set()
    await task
