"""Schema-level guarantees (I1, I2): the database itself must reject bad data.

Needs a migrated PostgreSQL. Set TEST_DATABASE_URL (plain postgresql:// DSN).
Every test runs inside a transaction that is rolled back.
"""

import datetime as dt
import os
import uuid

import asyncpg
import pytest
import pytest_asyncio
from asyncpg import exceptions as pgx

DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://rtbs:change_me@localhost:5432/rtbs"
)
T0 = dt.datetime(2030, 1, 1, 10, 0, tzinfo=dt.UTC)

BOOK = (
    "INSERT INTO bookings (user_id, resource_id, start_time, end_time, quantity, status,"
    " is_exclusive, idempotency_key, request_hash)"
    " VALUES ($1, $2, $3, $4, 1, 'CONFIRMED', $5, $6, 'h')"
)

pytestmark = pytest.mark.asyncio


def hour(n: int) -> dt.datetime:
    return T0 + dt.timedelta(hours=n)


@pytest_asyncio.fixture
async def conn():
    try:
        c = await asyncpg.connect(DSN, timeout=3)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database not reachable: {e}")
    tr = c.transaction()
    await tr.start()
    yield c
    await tr.rollback()
    await c.close()


async def make_user(c) -> uuid.UUID:
    return await c.fetchval(
        "INSERT INTO users (email, name, password_hash) VALUES ($1, 't', 'x') RETURNING user_id",
        f"{uuid.uuid4()}@test.com",
    )


async def make_resource(c, rtype: str, capacity: int) -> uuid.UUID:
    return await c.fetchval(
        "INSERT INTO resources (type, name, capacity, slot_minutes, open_time, close_time, timezone)"
        " VALUES ($1::resource_type, 'r', $2, 60, '00:00', '23:59', 'UTC') RETURNING resource_id",
        rtype,
        capacity,
    )


async def expect_error(c, exc, sql: str, *args) -> None:
    """Run sql in a savepoint so the outer transaction survives the expected failure."""
    with pytest.raises(exc):
        async with c.transaction():
            await c.execute(sql, *args)


async def test_overlapping_exclusive_bookings_rejected(conn):
    u1, u2, r = (
        await make_user(conn),
        await make_user(conn),
        await make_resource(conn, "SEAT", 1),
    )
    await conn.execute(BOOK, u1, r, hour(0), hour(2), True, "key-00000001")
    await expect_error(
        conn,
        pgx.ExclusionViolationError,
        BOOK,
        u2,
        r,
        hour(1),
        hour(3),
        True,
        "key-00000002",
    )


async def test_adjacent_exclusive_bookings_allowed(conn):
    u1, u2, r = (
        await make_user(conn),
        await make_user(conn),
        await make_resource(conn, "SEAT", 1),
    )
    await conn.execute(BOOK, u1, r, hour(0), hour(1), True, "key-00000001")
    await conn.execute(
        BOOK, u2, r, hour(1), hour(2), True, "key-00000002"
    )  # [start,end) semantics


async def test_cancelled_booking_does_not_block_seat(conn):
    u1, u2, r = (
        await make_user(conn),
        await make_user(conn),
        await make_resource(conn, "SEAT", 1),
    )
    await conn.execute(BOOK, u1, r, hour(0), hour(2), True, "key-00000001")
    await conn.execute(
        "UPDATE bookings SET status = 'CANCELLED' WHERE user_id = $1", u1
    )
    await conn.execute(BOOK, u2, r, hour(0), hour(2), True, "key-00000002")


async def test_overlap_allowed_for_non_exclusive_resource(conn):
    u1, u2, r = (
        await make_user(conn),
        await make_user(conn),
        await make_resource(conn, "ROOM", 10),
    )
    await conn.execute(BOOK, u1, r, hour(0), hour(2), False, "key-00000001")
    await conn.execute(
        BOOK, u2, r, hour(0), hour(2), False, "key-00000002"
    )  # capacity via ledger


async def test_ledger_cannot_exceed_capacity(conn):
    r = await make_resource(conn, "ROOM", 10)
    await expect_error(
        conn,
        pgx.CheckViolationError,
        "INSERT INTO slot_usage (resource_id, slot_start, used, capacity) VALUES ($1, $2, 11, 10)",
        r,
        hour(0),
    )


async def test_conditional_upsert_blocks_overbooking(conn):
    """The core ledger statement from LLD section 20.1."""
    r = await make_resource(conn, "ROOM", 10)
    sql = (
        "INSERT INTO slot_usage (resource_id, slot_start, used, capacity) VALUES ($1, $2, $3, 10)"
        " ON CONFLICT (resource_id, slot_start) DO UPDATE SET used = slot_usage.used + EXCLUDED.used"
        " WHERE slot_usage.used + EXCLUDED.used <= slot_usage.capacity RETURNING slot_start"
    )
    assert await conn.fetchval(sql, r, hour(0), 6) is not None
    assert await conn.fetchval(sql, r, hour(0), 4) is not None  # exactly full
    assert await conn.fetchval(sql, r, hour(0), 1) is None  # rejected, no row returned
    assert (
        await conn.fetchval("SELECT used FROM slot_usage WHERE resource_id=$1", r) == 10
    )


async def test_duplicate_idempotency_key_rejected(conn):
    u, r = await make_user(conn), await make_resource(conn, "ROOM", 10)
    await conn.execute(BOOK, u, r, hour(0), hour(1), False, "same-key-0001")
    await expect_error(
        conn,
        pgx.UniqueViolationError,
        BOOK,
        u,
        r,
        hour(5),
        hour(6),
        False,
        "same-key-0001",
    )


async def test_same_key_allowed_for_different_users(conn):
    u1, u2, r = (
        await make_user(conn),
        await make_user(conn),
        await make_resource(conn, "ROOM", 10),
    )
    await conn.execute(BOOK, u1, r, hour(0), hour(1), False, "same-key-0001")
    await conn.execute(BOOK, u2, r, hour(0), hour(1), False, "same-key-0001")


async def test_seat_must_have_capacity_one(conn):
    await expect_error(
        conn,
        pgx.CheckViolationError,
        "INSERT INTO resources (type, name, capacity, slot_minutes, open_time, close_time, timezone)"
        " VALUES ('SEAT', 's', 2, 60, '00:00', '23:59', 'UTC')",
    )


async def test_end_must_be_after_start(conn):
    u, r = await make_user(conn), await make_resource(conn, "ROOM", 10)
    await expect_error(
        conn,
        pgx.CheckViolationError,
        BOOK,
        u,
        r,
        hour(2),
        hour(2),
        False,
        "key-00000009",
    )
