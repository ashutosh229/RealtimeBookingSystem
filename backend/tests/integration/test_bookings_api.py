import uuid

import pytest

from app.messaging import outbox
from tests.integration.helpers import (
    at,
    book,
    create,
    fetch,
    fetchval,
    invariant_violations,  # noqa: F401
    make_user,
    new_key,
)


async def test_confirmed_booking_writes_everything(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    res = await create(client, admin, capacity=5, max_quantity_per_booking=3)
    rid = uuid.UUID(res["resource_id"])
    r = await book(client, student, rid, at(2, 9), at(2, 11), q=2)
    assert r.status_code == 201, r.text
    b = r.json()
    assert (
        b["status"] == "CONFIRMED"
        and b["quantity"] == 2
        and b["waitlist_position"] is None
    )
    assert r.headers["Location"] == f"/v1/bookings/{b['booking_id']}"
    bid = uuid.UUID(b["booking_id"])
    used = await fetch(
        "SELECT used FROM slot_usage WHERE resource_id = $1 ORDER BY slot_start", rid
    )
    assert [x["used"] for x in used] == [2, 2]
    hist = await fetch(
        "SELECT from_status::text f, to_status::text t FROM booking_status_history"
        " WHERE booking_id = $1",
        bid,
    )
    assert [(h["f"], h["t"]) for h in hist] == [("REQUESTED", "CONFIRMED")]
    assert (
        await fetchval(
            "SELECT decision_type FROM allocation_records WHERE booking_id = $1", bid
        )
        == "ADMIT"
    )
    assert (
        await fetchval(
            "SELECT event_type FROM outbox_events WHERE aggregate_id = $1", bid
        )
        == "BookingConfirmed"
    )
    assert await invariant_violations(rid) == 0


async def test_same_key_replays_without_a_second_booking(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    res = await create(client, admin)
    k = new_key()
    r1 = await book(client, student, res["resource_id"], at(2, 9), at(2, 10), k=k)
    r2 = await book(client, student, res["resource_id"], at(2, 9), at(2, 10), k=k)
    assert r1.status_code == r2.status_code == 201
    assert r2.json() == r1.json() and r2.headers["Idempotent-Replay"] == "true"
    assert "Idempotent-Replay" not in r1.headers
    assert (
        await fetchval(
            "SELECT count(*) FROM bookings WHERE user_id = $1", uuid.UUID(uid)
        )
        == 1
    )
    assert (
        await fetchval(
            "SELECT used FROM slot_usage WHERE resource_id = $1",
            uuid.UUID(res["resource_id"]),
        )
        == 1
    )


async def test_same_key_different_request_is_rejected(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    res = await create(client, admin)
    k = new_key()
    await book(client, student, res["resource_id"], at(2, 9), at(2, 10), k=k)
    r = await book(client, student, res["resource_id"], at(2, 9), at(2, 11), k=k)
    assert (
        r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    )


async def test_full_seat_returns_409_and_replays_it(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, b_id = await make_user(client)
    seat = await create(
        client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1
    )
    assert (
        await book(client, a, seat["resource_id"], at(2, 9), at(2, 10))
    ).status_code == 201
    k = new_key()
    r1 = await book(client, b, seat["resource_id"], at(2, 9), at(2, 10), k=k)
    assert (
        r1.status_code == 409 and r1.json()["error"]["code"] == "CAPACITY_UNAVAILABLE"
    )
    assert r1.json()["error"]["request_id"]
    r2 = await book(client, b, seat["resource_id"], at(2, 9), at(2, 10), k=k)
    assert r2.status_code == 409 and r2.headers["Idempotent-Replay"] == "true"
    assert (
        await fetchval(
            "SELECT count(*) FROM bookings WHERE user_id = $1", uuid.UUID(b_id)
        )
        == 0
    )


async def test_waitlist_when_full(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    c, _ = await make_user(client)
    seat = await create(
        client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1
    )
    rid = uuid.UUID(seat["resource_id"])
    await book(client, a, rid, at(2, 9), at(2, 10))
    k = new_key()
    rb = await book(client, b, rid, at(2, 9), at(2, 10), waitlist=True, k=k)
    rc = await book(client, c, rid, at(2, 9), at(2, 10), waitlist=True)
    assert rb.status_code == rc.status_code == 202
    jb, jc = rb.json(), rc.json()
    assert (
        jb["status"] == "WAITLISTED"
        and jb["waitlist_position"] == 1
        and jb["waitlist_id"]
    )
    assert jc["waitlist_position"] == 2
    assert (
        await book(client, b, rid, at(2, 9), at(2, 10), waitlist=True, k=k)
    ).json() == jb  # replay
    assert (
        await fetchval("SELECT used FROM slot_usage WHERE resource_id = $1", rid) == 1
    )  # ledger untouched
    assert (
        await fetchval(
            "SELECT count(*) FROM waitlist_entries WHERE resource_id = $1", rid
        )
        == 2
    )
    bid = uuid.UUID(jb["booking_id"])
    assert (
        await fetchval(
            "SELECT event_type FROM outbox_events WHERE aggregate_id = $1", bid
        )
        == "BookingWaitlisted"
    )
    assert (
        await fetchval(
            "SELECT decision_type FROM allocation_records WHERE booking_id = $1", bid
        )
        == "REJECT_FULL"
    )
    assert await invariant_violations(rid) == 0


async def test_waitlist_endpoint_confirms_when_there_is_room(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    seat = await create(
        client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1
    )
    r1 = await book(
        client, a, seat["resource_id"], at(2, 9), at(2, 10), path="/v1/waitlists"
    )
    r2 = await book(
        client, b, seat["resource_id"], at(2, 9), at(2, 10), path="/v1/waitlists"
    )
    assert (r1.status_code, r1.json()["status"]) == (201, "CONFIRMED")
    assert (r2.status_code, r2.json()["status"]) == (202, "WAITLISTED")


CASES = [
    (at(2, 9, 30), at(2, 10, 30), 1, "INVALID_INTERVAL"),
    (at(2, 7), at(2, 8), 1, "OUT_OF_HOURS"),
    (at(1, 9), at(1, 10), 1, "INVALID_INTERVAL"),
    (at(20, 9), at(20, 10), 1, "OUT_OF_HORIZON"),
    (at(2, 9), at(2, 10), 9, "QUANTITY_OUT_OF_RANGE"),
]


@pytest.mark.parametrize("start,end,q,code", CASES)
async def test_validation_failures_change_nothing(client, start, end, q, code):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    res = await create(client, admin)
    r = await book(client, student, res["resource_id"], start, end, q=q)
    assert r.status_code == 422 and r.json()["error"]["code"] == code
    rid = uuid.UUID(res["resource_id"])
    assert (
        await fetchval("SELECT count(*) FROM slot_usage WHERE resource_id = $1", rid)
        == 0
    )
    assert (
        await fetchval("SELECT count(*) FROM bookings WHERE resource_id = $1", rid) == 0
    )
    assert (
        await fetchval(
            "SELECT count(*) FROM idempotency_keys WHERE user_id = $1", uuid.UUID(uid)
        )
        == 0
    )


async def test_naive_timestamp_is_a_validation_error(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    res = await create(client, admin)
    r = await client.post(
        "/v1/bookings",
        headers={**student, "Idempotency-Key": new_key()},
        json={
            "resource_id": res["resource_id"],
            "start_time": "2030-01-02T09:00:00",
            "end_time": "2030-01-02T10:00:00",
        },
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_not_eligible(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client, group="general")
    res = await create(client, admin, eligible_groups=["pg"])
    r = await book(client, student, res["resource_id"], at(2, 9), at(2, 10))
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_ELIGIBLE"
    assert (
        await fetchval(
            "SELECT count(*) FROM slot_usage WHERE resource_id = $1",
            uuid.UUID(res["resource_id"]),
        )
        == 0
    )


async def test_idempotency_key_header_rules(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    res = await create(client, admin)
    body = {
        "resource_id": res["resource_id"],
        "start_time": at(2, 9).isoformat(),
        "end_time": at(2, 10).isoformat(),
    }
    r = await client.post("/v1/bookings", headers=student, json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "MALFORMED_REQUEST"
    r = await client.post(
        "/v1/bookings", headers={**student, "Idempotency-Key": "abc"}, json=body
    )
    assert r.status_code == 422


async def test_requires_auth(client):
    r = await client.post(
        "/v1/bookings", headers={"Idempotency-Key": new_key()}, json={}
    )
    assert r.status_code == 401


async def test_per_user_limit(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    other, _ = await make_user(client)
    res = await create(client, admin, capacity=10)
    rid = res["resource_id"]
    assert (await book(client, student, rid, at(2, 9), at(2, 10))).status_code == 201
    assert (await book(client, student, rid, at(2, 10), at(2, 11))).status_code == 201
    r = await book(client, student, rid, at(2, 11), at(2, 12))
    assert r.status_code == 409 and r.json()["error"]["code"] == "USER_LIMIT_REACHED"
    assert (await book(client, other, rid, at(2, 11), at(2, 12))).status_code == 201


async def test_inactive_and_unknown_resources(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    res = await create(client, admin)
    await client.post(
        f"/v1/admin/resources/{res['resource_id']}/deactivate", headers=admin
    )
    r = await book(client, student, res["resource_id"], at(2, 9), at(2, 10))
    assert r.status_code == 409 and r.json()["error"]["code"] == "RESOURCE_INACTIVE"
    r = await book(client, student, uuid.uuid4(), at(2, 9), at(2, 10))
    assert r.status_code == 404


async def test_failure_midway_rolls_back_everything(client, monkeypatch):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    res = await create(client, admin)
    rid, k = uuid.UUID(res["resource_id"]), new_key()
    original = outbox.add

    async def boom(*_a, **_k):
        raise RuntimeError("simulated crash after the ledger was updated")

    monkeypatch.setattr(outbox, "add", boom)
    with pytest.raises(RuntimeError):
        await book(client, student, rid, at(2, 9), at(2, 10), k=k)
    monkeypatch.setattr(outbox, "add", original)

    assert (
        await fetchval("SELECT count(*) FROM slot_usage WHERE resource_id = $1", rid)
        == 0
    )
    assert (
        await fetchval("SELECT count(*) FROM bookings WHERE resource_id = $1", rid) == 0
    )
    assert (
        await fetchval(
            "SELECT count(*) FROM idempotency_keys WHERE user_id = $1", uuid.UUID(uid)
        )
        == 0
    )
    r = await book(
        client, student, rid, at(2, 9), at(2, 10), k=k
    )  # the same key now works normally
    assert r.status_code == 201 and "Idempotent-Replay" not in r.headers
