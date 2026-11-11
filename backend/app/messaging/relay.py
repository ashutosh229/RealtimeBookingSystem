"""Outbox relay: publish committed outbox rows to RabbitMQ, mark them published after the confirm."""

import asyncio
import json
import logging
from uuid import UUID

import aio_pika
import asyncpg

from app.messaging.events import ROUTING_KEYS, parse_event
from app.messaging.topology import Topology, declare
from app.platform import db
from app.platform.config import get_settings

log = logging.getLogger("rtbs.relay")
MAX_ROW_ATTEMPTS = 10  # a row that cannot even be parsed is skipped after this many tries

_PENDING = (
    "SELECT id, event_id, aggregate_type, aggregate_id, event_type, schema_version, payload, created_at"
    " FROM outbox_events WHERE published_at IS NULL AND attempts < $2"
    " AND ($3::uuid[] IS NULL OR event_id = ANY($3))"
    " ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED"
)


def envelope(row) -> dict:
    return {
        "event_id": str(row["event_id"]),
        "event_type": row["event_type"],
        "schema_version": row["schema_version"],
        "occurred_at": row["created_at"].isoformat(),
        "aggregate_type": row["aggregate_type"],
        "aggregate_id": str(row["aggregate_id"]),
        "payload": row["payload"],
    }


async def relay_once(
    conn: asyncpg.Connection, exchange, *, batch: int = 100, only: list[UUID] | None = None
) -> int:
    """Publish up to `batch` pending events. A broker error aborts the batch (nothing is marked)."""
    async with conn.transaction():
        rows = await conn.fetch(_PENDING, batch, MAX_ROW_ATTEMPTS, only)
        for r in rows:
            env = envelope(r)
            try:
                parse_event(env)
            except Exception:  # noqa: BLE001
                log.exception("unpublishable outbox row %s", r["id"])
                await conn.execute(
                    "UPDATE outbox_events SET attempts = attempts + 1 WHERE id = $1",
                    r["id"],
                )
                continue
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(env).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    message_id=str(r["event_id"]),
                    type=r["event_type"],
                ),
                routing_key=ROUTING_KEYS[r["event_type"]],
                mandatory=True,  # an unroutable event raises instead of vanishing (I6)
                timeout=10,
            )
            await conn.execute(
                "UPDATE outbox_events SET published_at = now(), attempts = attempts + 1 WHERE id = $1",
                r["id"],
            )
    return len(rows)


async def run_relay(
    stop: asyncio.Event, *, topo: Topology = Topology(), amqp_url: str | None = None
) -> None:
    s = get_settings()
    connection = await aio_pika.connect_robust(amqp_url or s.amqp_url)
    try:
        channel = await connection.channel()  # publisher confirms are on by default
        declared = await declare(channel, topo)  # queues must exist before publishing
        log.info("relay started, polling every %s ms", s.relay_poll_ms)
        while not stop.is_set():
            try:
                async with db.get_pool().acquire() as conn:
                    n = await relay_once(conn, declared.exchange)
            except Exception:
                log.exception("relay cycle failed")
                n = 0
                await asyncio.sleep(1.0)
            if n == 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=s.relay_poll_ms / 1000)
                except TimeoutError:
                    pass
    finally:
        await connection.close()
        log.info("relay stopped")
