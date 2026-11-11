import asyncio
import json
import os
import uuid

import pytest
import pytest_asyncio
import redis.asyncio as aioredis

from app.availability import cache
from app.messaging.consumer import process
from app.platform import db
from app.platform.config import get_settings
from app.worker import handlers
from tests.integration.helpers import at, book, create, fetch, fetchval, make_user
from tests.integration.test_pipeline import body_of

URL = os.environ.get("TEST_REDIS_URL") or os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest_asyncio.fixture
async def redis_on():
    await cache.init(URL)
    try:
        await cache.get_client().ping()
    except Exception as e:  # noqa: BLE001
        await cache.close()
        pytest.skip(f"Redis not reachable: {e}")
    yield cache.get_client()
    await cache.close()


async def avail(client, headers, rid, day="2030-01-02", extra=None):
    r = await client.get(
        f"/v1/resources/{rid}/availability",
        params={"date": day},
        headers={**headers, **(extra or {})},
    )
    slots = (
        {s["start_time"][:13]: s["available"] for s in r.json()["slots"]}
        if r.status_code == 200
        else None
    )
    return r, slots


async def ver(redis, rid) -> int:
    return int(await redis.get(f"avail:ver:{rid}") or 0)


async def test_hit_miss_and_invalidation_by_booking_and_cancel(client, redis_on):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    rid = (await create(client, admin, capacity=5))["resource_id"]

    r1, s1 = await avail(client, student, rid)
    assert r1.headers["X-Cache"] == "MISS" and s1["2030-01-02T09"] == 5
    r2, _ = await avail(client, student, rid)
    assert (
        r2.headers["X-Cache"] == "HIT" and r2.json() == r1.json()
    )  # the entry carries its own as_of

    bk = (await book(client, student, rid, at(2, 9), at(2, 10), q=2)).json()
    r3, s3 = await avail(client, student, rid)
    assert r3.headers["X-Cache"] == "MISS" and s3["2030-01-02T09"] == 3  # read-your-writes
    assert (await avail(client, student, rid))[0].headers["X-Cache"] == "HIT"

    await client.post(f"/v1/bookings/{bk['booking_id']}/cancel", headers=student)
    r5, s5 = await avail(client, student, rid)
    assert r5.headers["X-Cache"] == "MISS" and s5["2030-01-02T09"] == 5


async def test_bypass_modes_and_unknown_resource(client, redis_on):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    rid = (await create(client, admin))["resource_id"]
    await avail(client, student, rid)
    r, _ = await avail(client, student, rid, extra={"Cache-Control": "no-cache"})
    assert r.headers["X-Cache"] == "BYPASS"
    rng = await client.get(
        f"/v1/resources/{rid}/availability",
        params={"from": at(2, 9).isoformat(), "to": at(2, 12).isoformat()},
        headers=student,
    )
    assert rng.status_code == 200 and rng.headers["X-Cache"] == "BYPASS"
    ghost, _ = await avail(client, student, uuid.uuid4())
    assert ghost.status_code == 404


async def test_deactivation_and_capacity_changes_are_never_served_stale(client, redis_on):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    rid = (await create(client, admin, capacity=5))["resource_id"]
    await avail(client, student, rid)
    assert (
        await client.patch(f"/v1/admin/resources/{rid}", json={"capacity": 8}, headers=admin)
    ).status_code == 200
    r, s = await avail(client, student, rid)
    assert r.headers["X-Cache"] == "MISS" and s["2030-01-02T09"] == 8

    await avail(client, student, rid)  # cached again
    assert (
        await client.post(f"/v1/admin/resources/{rid}/deactivate", headers=admin)
    ).status_code == 200
    gone, _ = await avail(client, student, rid)
    assert gone.status_code == 404  # not answered from the cache
    admin_view, _ = await avail(client, admin, rid)
    assert admin_view.status_code == 200 and admin_view.headers["X-Cache"] == "MISS"


async def test_a_fill_racing_an_invalidation_is_never_served(redis_on):
    rid = str(uuid.uuid4())

    async def loader_that_loses_the_race():
        await cache.bump(rid)  # a commit and its invalidation land while we are loading
        return {"v": "old"}, True

    assert (await cache.cached(rid, "2030-01-02", loader_that_loses_the_race))[1] == "MISS"
    calls = []

    async def fresh():
        calls.append(1)
        return {"v": "new"}, True

    data, state = await cache.cached(rid, "2030-01-02", fresh)
    assert (data, state, calls) == (
        {"v": "new"},
        "MISS",
        [1],
    )  # the old entry sits under a dead version
    assert (await cache.cached(rid, "2030-01-02", fresh))[1] == "HIT"


async def test_single_flight_limits_database_loads(redis_on):
    rid, calls = str(uuid.uuid4()), []

    async def slow():
        calls.append(1)
        await asyncio.sleep(0.05)
        return {"v": 1}, True

    results = await asyncio.gather(*(cache.cached(rid, "2030-01-02", slow) for _ in range(20)))
    assert len(calls) <= 3 and all(d == {"v": 1} for d, _ in results)


async def test_entries_expire(redis_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "avail_ttl_seconds", 1)
    rid = str(uuid.uuid4())

    async def loader():
        return {"v": 1}, True

    assert (await cache.cached(rid, "2030-01-02", loader))[1] == "MISS"
    assert (await cache.cached(rid, "2030-01-02", loader))[1] == "HIT"
    await asyncio.sleep(1.5)
    assert (await cache.cached(rid, "2030-01-02", loader))[1] == "MISS"


async def test_redis_failure_falls_back_to_the_loader(monkeypatch):
    broken = aioredis.from_url(
        "redis://127.0.0.1:1/0",
        decode_responses=True,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )
    monkeypatch.setattr(cache, "_client", broken)
    calls = []

    async def loader():
        calls.append(1)
        return {"v": 1}, True

    assert await cache.cached("x", "2030-01-02", loader) == (
        {"v": 1},
        "BYPASS",
    ) and calls == [1]
    await cache.bump("x")  # swallowed: layer 2 and the TTL cover it
    with pytest.raises(Exception):  # noqa: B017
        await cache.bump("x", strict=True)
    await broken.aclose()


async def test_cache_consumer_bumps_once_per_event_and_retries_on_failure(
    client, redis_on, monkeypatch
):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    other, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = seat["resource_id"]
    bk = (await book(client, student, rid, at(2, 9), at(2, 10))).json()
    wl = (await book(client, other, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    await client.post(f"/v1/bookings/{bk['booking_id']}/cancel", headers=student)
    pool = db.get_pool()

    confirmed = await body_of(bk["booking_id"], "BookingConfirmed")
    before = await ver(redis_on, rid)
    assert await process(pool, "cache", confirmed, handlers.cache_invalidate) == "processed"
    assert await ver(redis_on, rid) == before + 1
    assert await process(pool, "cache", confirmed, handlers.cache_invalidate) == "duplicate"
    assert await ver(redis_on, rid) == before + 1

    waitlisted = await body_of(
        wl["booking_id"], "BookingWaitlisted"
    )  # does not change availability
    assert await process(pool, "cache", waitlisted, handlers.cache_invalidate) == "processed"
    assert await ver(redis_on, rid) == before + 1

    cancelled = await body_of(bk["booking_id"], "BookingCancelled")
    eid = uuid.UUID(json.loads(cancelled)["event_id"])
    monkeypatch.setattr(cache, "_client", None)  # Redis "down" for this handler
    with pytest.raises(RuntimeError):
        await process(pool, "cache", cancelled, handlers.cache_invalidate)
    assert await fetchval("SELECT count(*) FROM processed_events WHERE event_id = $1", eid) == 0
    monkeypatch.setattr(cache, "_client", redis_on)
    assert await process(pool, "cache", cancelled, handlers.cache_invalidate) == "processed"
    assert await ver(redis_on, rid) == before + 2


async def test_resource_changes_emit_resource_updated(client):
    admin, _ = await make_user(client, "admin", "staff")
    res = await create(client, admin, capacity=5)
    rid = uuid.UUID(res["resource_id"])
    await client.patch(
        f"/v1/admin/resources/{rid}",
        json={"name": f"itest-renamed-{rid.hex[:6]}"},
        headers=admin,
    )
    await client.post(f"/v1/admin/resources/{rid}/deactivate", headers=admin)
    rows = await fetch(
        "SELECT payload->>'change' AS c FROM outbox_events WHERE aggregate_id = $1"
        " AND event_type = 'ResourceUpdated' ORDER BY id",
        rid,
    )
    assert [r["c"] for r in rows] == ["created", "updated", "deactivated"]


async def test_force_deactivation_emits_exactly_one_resource_event(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    rid = (await create(client, admin))["resource_id"]
    await book(client, student, rid, at(2, 9), at(2, 10))
    assert (
        await client.post(
            f"/v1/admin/resources/{rid}/deactivate", json={"force": True}, headers=admin
        )
    ).status_code == 200
    n = await fetchval(
        "SELECT count(*) FROM outbox_events WHERE aggregate_id = $1 AND event_type = 'ResourceUpdated'"
        " AND payload->>'change' = 'deactivated'",
        uuid.UUID(rid),
    )
    assert n == 1
