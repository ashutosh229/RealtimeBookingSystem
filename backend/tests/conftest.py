import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

# Defaults so unit tests run without a .env; real environments override these.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://rtbs:change_me@localhost:5432/rtbs")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-unit-test-secret-1234")

DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://rtbs:change_me@localhost:5432/rtbs")


@pytest_asyncio.fixture
async def pool():
    try:
        p = await asyncpg.create_pool(DSN, min_size=1, max_size=30, timeout=3)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database not reachable: {e}")
    yield p
    await p.close()


@pytest_asyncio.fixture
async def new_resource(pool):
    """Factory for committed test resources; cleaned up afterwards."""
    ids: list[uuid.UUID] = []

    async def make(capacity: int, rtype: str = "ROOM") -> uuid.UUID:
        rid = await pool.fetchval(
            "INSERT INTO resources (type, name, capacity, slot_minutes, open_time, close_time, timezone)"
            " VALUES ($1::resource_type, $2, $3, 60, '00:00', '23:59', 'UTC') RETURNING resource_id",
            rtype,
            f"itest-led-{uuid.uuid4().hex[:8]}",
            capacity,
        )
        ids.append(rid)
        return rid

    yield make
    await pool.execute("DELETE FROM slot_usage WHERE resource_id = ANY($1)", ids)
    await pool.execute("DELETE FROM resources WHERE resource_id = ANY($1)", ids)


@pytest_asyncio.fixture
async def client(monkeypatch):
    # Imports live inside the fixture so the env defaults at the top of this file are set first.
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.platform import clock, db
    from tests.integration.helpers import NOW

    monkeypatch.setattr(clock, "now", lambda: NOW)
    try:
        await db.init_pool()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database not reachable: {e}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    async with db.get_pool().acquire() as conn:
        rs = "(SELECT resource_id FROM resources WHERE name LIKE 'itest-%')"
        bk = f"(SELECT booking_id FROM bookings WHERE resource_id IN {rs})"
        await conn.execute(f"DELETE FROM outbox_events WHERE aggregate_id IN {bk}")
        for t in ("allocation_records", "booking_status_history", "waitlist_entries"):
            await conn.execute(f"DELETE FROM {t} WHERE booking_id IN {bk}")
        await conn.execute(f"DELETE FROM bookings WHERE resource_id IN {rs}")
        await conn.execute(f"DELETE FROM slot_usage WHERE resource_id IN {rs}")
        await conn.execute("DELETE FROM resources WHERE name LIKE 'itest-%'")
        users = "(SELECT user_id FROM users WHERE email LIKE '%@itest.local')"
        await conn.execute(f"DELETE FROM idempotency_keys WHERE user_id IN {users}")
        await conn.execute(f"DELETE FROM refresh_tokens WHERE user_id IN {users}")
        await conn.execute("DELETE FROM users WHERE email LIKE '%@itest.local'")
    await db.close_pool()
