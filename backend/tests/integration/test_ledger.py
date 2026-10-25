import datetime as dt

import pytest

from app.booking import ledger

T0 = dt.datetime(2030, 1, 7, 9, tzinfo=dt.UTC)


def slots(n: int, offset: int = 0) -> list[dt.datetime]:
    return [T0 + dt.timedelta(hours=offset + i) for i in range(n)]


async def used(pool, rid) -> dict:
    rows = await pool.fetch("SELECT slot_start, used FROM slot_usage WHERE resource_id = $1", rid)
    return {r["slot_start"]: r["used"] for r in rows}


async def test_fills_exactly_to_capacity_then_refuses(pool, new_resource):
    rid = await new_resource(10)
    async with pool.acquire() as c:
        assert await ledger.acquire(c, rid, slots(1), 6, 10)
        assert await ledger.acquire(c, rid, slots(1), 4, 10)
        assert not await ledger.acquire(c, rid, slots(1), 1, 10)
    assert await used(pool, rid) == {T0: 10}


async def test_failure_leaves_no_partial_changes(pool, new_resource):
    rid = await new_resource(3)
    async with pool.acquire() as c:
        assert await ledger.acquire(c, rid, slots(1, offset=1), 3, 3)  # middle slot is full
        assert not await ledger.acquire(c, rid, slots(3), 1, 3)  # spans the full slot
    assert await used(pool, rid) == {T0 + dt.timedelta(hours=1): 3}  # slots 0 and 2 untouched


async def test_quantity_above_capacity_is_refused(pool, new_resource):
    rid = await new_resource(3)
    async with pool.acquire() as c:
        assert not await ledger.acquire(c, rid, slots(1), 4, 3)
    assert await used(pool, rid) == {}


async def test_release_restores_capacity(pool, new_resource):
    rid = await new_resource(5)
    async with pool.acquire() as c:
        assert await ledger.acquire(c, rid, slots(2), 5, 5)
        await ledger.release(c, rid, slots(2), 5)
        assert await ledger.acquire(c, rid, slots(2), 5, 5)
    assert await used(pool, rid) == {T0: 5, T0 + dt.timedelta(hours=1): 5}


async def test_release_more_than_acquired_raises_and_changes_nothing(pool, new_resource):
    rid = await new_resource(5)
    async with pool.acquire() as c:
        assert await ledger.acquire(c, rid, slots(2), 2, 5)
        with pytest.raises(ledger.InvariantViolation):
            await ledger.release(c, rid, slots(2), 3)
        with pytest.raises(ledger.InvariantViolation):
            await ledger.release(c, rid, slots(1, offset=5), 1)  # never-booked slot
    assert await used(pool, rid) == {T0: 2, T0 + dt.timedelta(hours=1): 2}


async def test_acquire_rolls_back_with_the_outer_transaction(pool, new_resource):
    rid = await new_resource(5)
    async with pool.acquire() as c:
        tr = c.transaction()
        await tr.start()
        assert await ledger.acquire(c, rid, slots(1), 2, 5)
        await tr.rollback()  # e.g. booking insert failed
    assert await used(pool, rid) == {}


@pytest.mark.parametrize("bad_slots,q", [([], 1), (slots(1), 0), ([T0, T0], 1)])
async def test_invalid_arguments(pool, new_resource, bad_slots, q):
    rid = await new_resource(5)
    async with pool.acquire() as c:
        with pytest.raises(ValueError):
            await ledger.acquire(c, rid, bad_slots, q, 5)
        with pytest.raises(ValueError):
            await ledger.release(c, rid, bad_slots, q)
