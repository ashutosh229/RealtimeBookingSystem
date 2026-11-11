"""Generic consumer: idempotent processing, retry with backoff, dead-letter."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping

import aio_pika
import asyncpg

from app.messaging.events import _Envelope, parse_event
from app.messaging.topology import Topology, declare, next_hop
from app.platform.config import get_settings

log = logging.getLogger("rtbs.consumer")
Handler = Callable[[asyncpg.Connection, _Envelope], Awaitable[None]]


class BadMessage(Exception):
    """The body is not a valid event. Retrying cannot help."""


async def process(pool: asyncpg.Pool, consumer: str, body: bytes, handler: Handler) -> str:
    """Run `handler` exactly once per (consumer, event). The dedupe row and the handler's own writes
    commit together; if the handler raises, the dedupe row rolls back so a retry is processed.
    """
    try:
        event = parse_event(json.loads(body))
    except Exception as e:  # noqa: BLE001
        raise BadMessage(str(e)) from e
    async with pool.acquire() as conn, conn.transaction():
        fresh = await conn.fetchval(
            "INSERT INTO processed_events (consumer, event_id) VALUES ($1, $2)"
            " ON CONFLICT DO NOTHING RETURNING 1",
            consumer,
            event.event_id,
        )
        if not fresh:
            return "duplicate"
        await handler(conn, event)
    return "processed"


async def _forward(channel, target: str, message, attempt: int, err: str) -> None:
    headers = {**(message.headers or {}), "x-attempt": attempt, "x-error": err[:200]}
    await channel.default_exchange.publish(
        aio_pika.Message(
            body=message.body,
            headers=headers,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type=message.content_type,
            message_id=message.message_id,
        ),
        routing_key=target,
    )


def _callback(pool, channel, topo, name, handler, max_attempts, inflight):
    async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
        inflight["n"] += 1
        try:
            attempt = int((message.headers or {}).get("x-attempt", 0))
            try:
                outcome = await process(pool, name, message.body, handler)
                log.debug("%s %s: %s", name, message.message_id, outcome)
            except BadMessage as e:
                log.warning("%s: unparseable message sent to the DLQ: %s", name, e)
                await _forward(channel, topo.dlq(name), message, attempt, str(e))
            except Exception as e:  # noqa: BLE001
                hop = next_hop(topo, name, attempt, max_attempts)
                log.warning(
                    "%s: attempt %s failed (%s), forwarding to %s",
                    name,
                    attempt + 1,
                    e,
                    hop,
                )
                await _forward(channel, hop, message, attempt + 1, str(e))
            await message.ack()  # only after the message is safely processed or forwarded
        except Exception:  # noqa: BLE001
            log.exception("%s: could not settle message, requeueing", name)
            await message.nack(requeue=True)
        finally:
            inflight["n"] -= 1

    return on_message


async def run_consumers(
    stop: asyncio.Event,
    *,
    handlers: Mapping[str, Handler],
    topo: Topology = Topology(),
    amqp_url: str | None = None,
    max_attempts: int | None = None,
) -> None:
    from app.platform import (
        db,
    )  # local import keeps this module importable without a pool

    s = get_settings()
    attempts = max_attempts or s.max_delivery_attempts
    connection = await aio_pika.connect_robust(amqp_url or s.amqp_url)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=s.consumer_prefetch)
        declared = await declare(channel, topo)
        inflight = {"n": 0}
        tags = []
        for name, handler in handlers.items():
            queue = declared.queues[name]
            cb = _callback(db.get_pool(), channel, topo, name, handler, attempts, inflight)
            tags.append((queue, await queue.consume(cb)))
        log.info("consuming: %s", ", ".join(handlers))
        await stop.wait()
        for queue, tag in tags:
            await queue.cancel(tag)
        for _ in range(100):  # let in-flight messages finish (up to 10 s)
            if inflight["n"] == 0:
                break
            await asyncio.sleep(0.1)
    finally:
        await connection.close()
        log.info("consumers stopped")
