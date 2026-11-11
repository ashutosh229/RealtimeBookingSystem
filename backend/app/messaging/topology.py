"""RabbitMQ layout. Declared idempotently by the relay and by every consumer."""

from dataclasses import dataclass

import aio_pika
from aio_pika import ExchangeType

RETRY_DELAYS_MS = (5_000, 30_000, 120_000)
BINDINGS: dict[str, tuple[str, ...]] = {
    "notify": ("booking.*",),
    "promote": ("capacity.released",),
}


@dataclass(frozen=True)
class Topology:
    prefix: str = ""  # tests use a unique prefix so they never touch the real queues
    delays_ms: tuple[int, ...] = RETRY_DELAYS_MS

    @property
    def exchange_name(self) -> str:
        return f"{self.prefix}booking.events"

    def queue(self, name: str) -> str:
        return f"{self.prefix}q.{name}"

    def dlq(self, name: str) -> str:
        return f"{self.queue(name)}.dlq"

    def retry(self, name: str, i: int) -> str:
        return f"{self.queue(name)}.retry.{i}"

    def all_queues(self) -> list[str]:
        out = []
        for n in BINDINGS:
            out += [self.queue(n), self.dlq(n)] + [
                self.retry(n, i) for i in range(len(self.delays_ms))
            ]
        return out


@dataclass
class Declared:
    exchange: aio_pika.abc.AbstractExchange
    queues: dict[str, aio_pika.abc.AbstractQueue]


def next_hop(topo: Topology, name: str, attempt: int, max_attempts: int) -> str:
    """Queue a failed message is forwarded to. `attempt` = deliveries that already failed (0 on the first)."""
    if attempt + 1 >= max_attempts:
        return topo.dlq(name)
    return topo.retry(name, min(attempt, len(topo.delays_ms) - 1))


async def declare(channel, topo: Topology = Topology()) -> Declared:
    exchange = await channel.declare_exchange(topo.exchange_name, ExchangeType.TOPIC, durable=True)
    queues = {}
    for name, keys in BINDINGS.items():
        q = await channel.declare_queue(topo.queue(name), durable=True)
        for key in keys:
            await q.bind(exchange, routing_key=key)
        queues[name] = q
        await channel.declare_queue(topo.dlq(name), durable=True)
        for i, ms in enumerate(topo.delays_ms):
            await channel.declare_queue(
                topo.retry(name, i),
                durable=True,
                arguments={
                    "x-message-ttl": ms,
                    "x-dead-letter-exchange": "",  # default exchange ...
                    "x-dead-letter-routing-key": topo.queue(
                        name
                    ),  # ... straight back to this consumer
                },
            )
    return Declared(exchange, queues)
