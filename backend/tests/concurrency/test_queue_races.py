import asyncio
import uuid
from collections import Counter

from app.platform import db
from app.worker import sweeper
from tests.concurrency.test_promotion_races import seat_with_waiters
from tests.integration.helpers import (
    at,
    book,
    invariant_violations,
    make_user,
)


async def locked_cycle(rid):
    async with db.get_pool().acquire() as conn:
        return await sweeper.run_locked(conn, [uuid.UUID(rid)])


async def test_newcomers_cannot_jump_the_queue_under_load(client):
    rid, waiters = await seat_with_waiters(client, 5)  # the seat is already free, 5 are waiting
    newcomers = await asyncio.gather(*(make_user(client) for _ in range(10)))
    out = await asyncio.gather(
        *(book(client, h, rid, at(2, 9), at(2, 10), waitlist=True) for h, _ in newcomers),
        *(locked_cycle(rid) for _ in range(4)),
    )
    assert Counter(r.status_code for r in out[:10]) == {
        202: 10
    }  # nobody confirmed ahead of the queue
    assert any(r is not None for r in out[10:])  # at least one sweeper actually ran
    confirmed = await db_confirmed(rid)
    assert confirmed == [waiters[0][1]]  # exactly the earliest waiter
    assert await invariant_violations(rid) == 0


async def db_confirmed(rid) -> list[str]:
    async with db.get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT booking_id FROM bookings WHERE resource_id = $1 AND status = 'CONFIRMED'",
            uuid.UUID(rid),
        )
    return [str(r["booking_id"]) for r in rows]
