"""Real concurrency: many connections, each in its own committed transaction."""

import asyncio
import datetime as dt
import random

import asyncpg

from app.booking import ledger

T0 = dt.datetime(2030, 1, 7, 9, tzinfo=dt.UTC)
SLOTS6 = [T0 + dt.timedelta(hours=i) for i in range(6)]


async def attempt(pool, rid, slots, q, cap) -> bool:
    """One acquire in its own transaction; retried on deadlock, as the booking service will do."""
    for _ in range(5):
        try:
            async with pool.acquire() as c, c.transaction():
                return await ledger.acquire(c, rid, slots, q, cap)
        except asyncpg.DeadlockDetectedError:
            await asyncio.sleep(random.random() / 50)
    raise AssertionError("deadlock persisted after 5 retries")


async def test_last_units_race_exactly_capacity_wins(pool, new_resource):
    cap = 10
    rid = await new_resource(cap)
    results = await asyncio.gather(*(attempt(pool, rid, SLOTS6[:1], 1, cap) for _ in range(100)))
    assert sum(results) == cap
    assert await pool.fetchval("SELECT used FROM slot_usage WHERE resource_id = $1", rid) == cap


async def test_single_seat_100_contenders_one_winner(pool, new_resource):
    rid = await new_resource(1, "SEAT")
    results = await asyncio.gather(*(attempt(pool, rid, SLOTS6[:2], 1, 1) for _ in range(100)))
    assert sum(results) == 1


async def test_overlapping_ranges_never_oversubscribe(pool, new_resource):
    cap = 5
    rid = await new_resource(cap)
    rng = random.Random(42)
    reqs = []
    for _ in range(80):
        start, length, q = rng.randrange(6), rng.randint(1, 3), rng.randint(1, 3)
        reqs.append((SLOTS6[start : start + length], q))
    results = await asyncio.gather(*(attempt(pool, rid, s, q, cap) for s, q in reqs))

    expected = {s: 0 for s in SLOTS6}
    for (s, q), ok in zip(reqs, results, strict=True):
        if ok:
            for slot in s:
                expected[slot] += q
    rows = await pool.fetch("SELECT slot_start, used FROM slot_usage WHERE resource_id = $1", rid)
    actual = {r["slot_start"]: r["used"] for r in rows}
    for slot, total in expected.items():
        assert actual.get(slot, 0) == total <= cap, (
            f"slot {slot}: ledger {actual.get(slot, 0)}, accepted {total}"
        )
    assert any(results) and not all(results), "test did not create real contention"


async def test_acquire_release_churn_ends_at_zero(pool, new_resource):
    cap = 3
    rid = await new_resource(cap)

    async def churn():
        for _ in range(5):
            if await attempt(pool, rid, SLOTS6[:1], 1, cap):
                async with pool.acquire() as c:
                    await ledger.release(c, rid, SLOTS6[:1], 1)

    await asyncio.gather(*(churn() for _ in range(20)))
    assert await pool.fetchval("SELECT used FROM slot_usage WHERE resource_id = $1", rid) == 0
