import uuid
from datetime import timedelta

from app.platform import clock, db
from app.worker import sweeper
from tests.integration.helpers import (
    at,
    book,
    create,
    fetch,
    fetchval,
    invariant_violations,
    make_user,
)
from tests.integration.test_promotion import cancel, status


def uid(x) -> uuid.UUID:
    return uuid.UUID(str(x))


async def cycle(*rids):
    async with db.get_pool().acquire() as conn:
        return await sweeper.run_cycle(conn, [uid(r) for r in rids])


async def make_seat(client):
    admin, _ = await make_user(client, "admin", "staff")
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    return admin, seat["resource_id"]


async def test_cycle_promotes_after_a_cancellation(client):
    _, rid = await make_seat(client)
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    bk_a = (await book(client, a, rid, at(2, 9), at(2, 10))).json()
    bk_b = (await book(client, b, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    assert (await cycle(rid))["promoted"] == 0
    await cancel(client, a, bk_a["booking_id"])
    assert (await cycle(rid))["promoted"] == 1
    assert await status(bk_b["booking_id"]) == "CONFIRMED"
    assert (await cycle(rid))["promoted"] == 0
    assert await invariant_violations(rid) == 0


async def test_queue_jumping_is_blocked(client):
    _, rid = await make_seat(client)
    owner, _ = await make_user(client)
    waiter, _ = await make_user(client)
    newcomer, _ = await make_user(client)
    bk_o = (await book(client, owner, rid, at(2, 9), at(2, 10))).json()
    bk_w = (await book(client, waiter, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    await cancel(client, owner, bk_o["booking_id"])  # the slot is free, but a queue exists

    r = await book(client, newcomer, rid, at(2, 9), at(2, 10))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CAPACITY_UNAVAILABLE"
    assert "waitlist" in r.json()["error"]["message"]
    assert (
        await fetchval(
            "SELECT COALESCE(SUM(used), 0) FROM slot_usage WHERE resource_id = $1",
            uid(rid),
        )
        == 0
    )

    r = await book(client, newcomer, rid, at(2, 9), at(2, 10), waitlist=True)
    assert r.status_code == 202 and r.json()["waitlist_position"] == 2
    reason = await fetchval(
        "SELECT inputs->>'reason' FROM allocation_records WHERE booking_id = $1",
        uid(r.json()["booking_id"]),
    )
    assert reason == "queue_exists"

    assert (
        await book(client, newcomer, rid, at(2, 12), at(2, 13))
    ).status_code == 201  # other window: no queue

    assert (await cycle(rid))["promoted"] == 1
    assert await status(bk_w["booking_id"]) == "CONFIRMED"  # the earlier waiter wins
    assert await status(r.json()["booking_id"]) == "WAITLISTED"
    assert await invariant_violations(rid) == 0


async def test_expiry_and_completion(client, monkeypatch):
    _, rid = await make_seat(client)
    owner, _ = await make_user(client)
    waiter, _ = await make_user(client)
    bk_o = (await book(client, owner, rid, at(2, 9), at(2, 10))).json()
    bk_w = (await book(client, waiter, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    wid = uid(bk_w["booking_id"])

    monkeypatch.setattr(
        clock, "now", lambda: at(2, 9, 30)
    )  # the slot has started; the queue is moot
    first = await cycle(rid)
    assert (first["expired"], first["promoted"], first["completed"]) == (1, 0, 0)
    assert await status(bk_w["booking_id"]) == "EXPIRED"
    assert (
        await fetchval("SELECT status::text FROM waitlist_entries WHERE booking_id = $1", wid)
        == "EXPIRED"
    )
    hist = await fetch(
        "SELECT to_status::text t, reason FROM booking_status_history WHERE booking_id = $1"
        " ORDER BY id",
        wid,
    )
    assert [(h["t"], h["reason"]) for h in hist] == [
        ("WAITLISTED", "created"),
        ("EXPIRED", "waitlist_expired"),
    ]
    events = await fetch(
        "SELECT event_type FROM outbox_events WHERE aggregate_id = $1 ORDER BY id", wid
    )
    assert [e["event_type"] for e in events] == ["BookingWaitlisted", "BookingExpired"]
    assert (
        await fetchval("SELECT used FROM slot_usage WHERE resource_id = $1", uid(rid)) == 1
    )  # owner untouched

    monkeypatch.setattr(clock, "now", lambda: at(2, 10, 30))  # the owner's booking has now ended
    assert (await cycle(rid))["completed"] == 1
    assert await status(bk_o["booking_id"]) == "COMPLETED"
    assert (
        await fetchval("SELECT used FROM slot_usage WHERE resource_id = $1", uid(rid)) == 1
    )  # past usage stays
    assert await invariant_violations(rid) == 0
    r = await cancel(client, owner, bk_o["booking_id"])  # terminal: returned unchanged
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    assert (await cycle(rid))["completed"] == 0


async def test_purge_removes_only_old_idempotency_keys(client):
    _, uid_ = await make_user(client)
    user = uid(uid_)
    async with db.get_pool().acquire() as conn:
        for key, age in (
            ("old-key-0001", timedelta(hours=25)),
            ("new-key-0002", timedelta(hours=1)),
        ):
            await conn.execute(
                "INSERT INTO idempotency_keys (user_id, idem_key, request_hash, response_code, response_body,"
                " created_at) VALUES ($1, $2, 'h', 201, '{}'::jsonb, now() - $3::interval)",
                user,
                key,
                age,
            )
        await sweeper.purge(conn)
    left = await fetch("SELECT idem_key FROM idempotency_keys WHERE user_id = $1", user)
    assert [r["idem_key"] for r in left] == ["new-key-0002"]


async def test_only_one_sweeper_runs_at_a_time(client):
    async with db.get_pool().acquire() as holder, db.get_pool().acquire() as other:
        await holder.fetchval("SELECT pg_advisory_lock(hashtext($1))", sweeper.SWEEPER_LOCK)
        try:
            assert await sweeper.run_locked(other, []) is None  # busy: skipped, not queued
        finally:
            await holder.fetchval("SELECT pg_advisory_unlock(hashtext($1))", sweeper.SWEEPER_LOCK)
        assert await sweeper.run_locked(other, []) is not None
