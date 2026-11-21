"""Inspect and replay dead-lettered messages (ADR-0024).

    python -m app.messaging.dlq list                 # depth of every DLQ, first few errors
    python -m app.messaging.dlq replay notify        # move up to --limit messages back to q.notify
    python -m app.messaging.dlq replay all --limit 50
    python -m app.messaging.dlq purge cache          # discard a DLQ (asks for --yes)

Replaying resets the attempt counter, so a message gets a full set of retries again. Replay is
at-least-once: the message is published before it is acknowledged, and the consumers' dedupe
table makes a repeat harmless. Fix the cause first, or the message returns here after 5 attempts.
"""

import argparse
import asyncio

import aio_pika

from app.messaging.topology import BINDINGS, Topology, declare
from app.platform.config import get_settings


def _names(which: str) -> list[str]:
    if which == "all":
        return list(BINDINGS)
    if which not in BINDINGS:
        raise SystemExit(f"unknown consumer {which!r}: use one of {', '.join(BINDINGS)} or all")
    return [which]


async def depth(channel, topo: Topology, name: str) -> int:
    q = await channel.declare_queue(topo.dlq(name), durable=True)
    return q.declaration_result.message_count


async def peek(channel, topo: Topology, name: str, n: int) -> list[dict]:
    """Look at up to n messages without losing any: they are held, then requeued together."""
    q = await channel.declare_queue(topo.dlq(name), durable=True)
    held, out = [], []
    for _ in range(n):
        m = await q.get(no_ack=False, fail=False)
        if m is None:
            break
        held.append(m)
        out.append(
            {
                "message_id": m.message_id,
                "attempts": (m.headers or {}).get("x-attempt"),
                "error": (m.headers or {}).get("x-error"),
                "body": m.body[:200].decode(errors="replace"),
            }
        )
    for m in held:
        await m.nack(requeue=True)
    return out


async def replay(channel, topo: Topology, name: str, limit: int) -> int:
    dlq = await channel.declare_queue(topo.dlq(name), durable=True)
    moved = 0
    while moved < limit:
        m = await dlq.get(no_ack=False, fail=False)
        if m is None:
            break
        headers = {k: v for k, v in (m.headers or {}).items() if k not in ("x-attempt", "x-error")}
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=m.body,
                headers=headers,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type=m.content_type,
                message_id=m.message_id,
            ),
            routing_key=topo.queue(name),
        )
        await m.ack()  # only after the copy is published
        moved += 1
    return moved


async def run(args, topo: Topology = Topology(), amqp_url: str | None = None) -> None:
    connection = await aio_pika.connect_robust(amqp_url or get_settings().amqp_url)
    try:
        channel = await connection.channel(publisher_confirms=True)
        await declare(channel, topo)
        names = _names(args.queue)
        for name in names:
            if args.cmd == "list":
                n = await depth(channel, topo, name)
                print(f"{topo.dlq(name)}: {n} message(s)")
                for item in await peek(channel, topo, name, args.peek) if n else []:
                    print(f"  {item['message_id']}  attempts={item['attempts']}  {item['error']}")
            elif args.cmd == "replay":
                print(f"{topo.dlq(name)}: replayed {await replay(channel, topo, name, args.limit)}")
            elif args.cmd == "purge":
                if not args.yes:
                    raise SystemExit("purge discards messages for good; add --yes to confirm")
                q = await channel.declare_queue(topo.dlq(name), durable=True)
                print(f"{topo.dlq(name)}: purged {(await q.purge()).message_count}")
    finally:
        await connection.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("queue", nargs="?", default="all")
    ls.add_argument("--peek", type=int, default=3)
    rp = sub.add_parser("replay")
    rp.add_argument("queue")
    rp.add_argument("--limit", type=int, default=100)
    pg = sub.add_parser("purge")
    pg.add_argument("queue")
    pg.add_argument("--yes", action="store_true")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
