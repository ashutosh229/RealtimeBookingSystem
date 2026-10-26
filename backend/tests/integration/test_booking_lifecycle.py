import uuid

from tests.integration.helpers import (
    at,
    book,
    create,
    fetch,
    fetchval,
    invariant_violations,
    make_user,
)


async def cancel(c, headers, bid):
    return await c.post(f"/v1/bookings/{bid}/cancel", headers=headers)


async def event_types(bid) -> list[str]:
    rows = await fetch(
        "SELECT event_type FROM outbox_events WHERE aggregate_id = $1 ORDER BY id",
        uuid.UUID(bid),
    )
    return [r["event_type"] for r in rows]


async def total_used(rid) -> int:
    return await fetchval(
        "SELECT COALESCE(SUM(used), 0) FROM slot_usage WHERE resource_id = $1", rid
    )


async def test_cancel_confirmed_releases_capacity_and_is_idempotent(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = uuid.UUID(seat["resource_id"])
    bk = (await book(client, a, rid, at(2, 9), at(2, 11))).json()
    assert await total_used(rid) == 2

    r = await cancel(client, a, bk["booking_id"])
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert await total_used(rid) == 0
    assert await event_types(bk["booking_id"]) == [
        "BookingConfirmed",
        "BookingCancelled",
        "CapacityReleased",
    ]
    hist = await fetch(
        "SELECT to_status::text t FROM booking_status_history WHERE booking_id = $1 ORDER BY id",
        uuid.UUID(bk["booking_id"]),
    )
    assert [h["t"] for h in hist] == ["CONFIRMED", "CANCELLED"]

    again = await cancel(client, a, bk["booking_id"])  # repeat: unchanged, no second release
    assert again.status_code == 200 and again.json()["status"] == "CANCELLED"
    assert await total_used(rid) == 0
    assert len(await event_types(bk["booking_id"])) == 3

    assert (
        await book(client, b, rid, at(2, 9), at(2, 11))
    ).status_code == 201  # capacity is reusable
    assert await invariant_violations(rid) == 0


async def test_cancel_waitlisted_touches_no_capacity(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = uuid.UUID(seat["resource_id"])
    await book(client, a, rid, at(2, 9), at(2, 10))
    wl = (await book(client, b, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    r = await cancel(client, b, wl["booking_id"])
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert (
        await fetchval(
            "SELECT status::text FROM waitlist_entries WHERE booking_id = $1",
            uuid.UUID(wl["booking_id"]),
        )
        == "CANCELLED"
    )
    assert await event_types(wl["booking_id"]) == [
        "BookingWaitlisted",
        "BookingCancelled",
    ]
    assert await total_used(rid) == 1  # a's seat untouched
    assert await invariant_violations(rid) == 0


async def test_ownership_and_admin_override(client):
    admin, _ = await make_user(client, "admin", "staff")
    owner, _ = await make_user(client)
    other, _ = await make_user(client)
    room = await create(client, admin)
    bk = (await book(client, owner, room["resource_id"], at(2, 9), at(2, 10))).json()
    bid = bk["booking_id"]
    assert (await cancel(client, other, bid)).status_code == 404
    assert (await client.get(f"/v1/bookings/{bid}", headers=other)).status_code == 404
    assert (await client.get(f"/v1/bookings/{bid}", headers=admin)).status_code == 200
    assert (await cancel(client, admin, bid)).status_code == 200
    reason = await fetchval(
        "SELECT reason FROM booking_status_history WHERE booking_id = $1"
        " AND to_status = 'CANCELLED'",
        uuid.UUID(bid),
    )
    assert reason == "admin_cancel"
    assert (await cancel(client, owner, str(uuid.uuid4()))).status_code == 404


async def test_cancellation_window(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    room = await create(client, admin, capacity=5)
    rid = uuid.UUID(room["resource_id"])
    bk = (await book(client, student, rid, at(2, 9), at(2, 10))).json()
    # frozen "now" is Jan 1 09:30, so the booking starts in 23.5 h; require 2000 min (33 h) notice
    await fetchval(
        "UPDATE resources SET min_cancel_notice_minutes = 2000 WHERE resource_id = $1 RETURNING 1",
        rid,
    )
    r = await cancel(client, student, bk["booking_id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "CANCELLATION_WINDOW_CLOSED"
    assert await total_used(rid) == 1  # nothing changed
    assert (
        await cancel(client, admin, bk["booking_id"])
    ).status_code == 200  # admin bypasses notice
    await fetchval(
        "UPDATE resources SET min_cancel_notice_minutes = 60 WHERE resource_id = $1 RETURNING 1",
        rid,
    )
    bk2 = (await book(client, student, rid, at(2, 11), at(2, 12))).json()
    assert (await cancel(client, student, bk2["booking_id"])).status_code == 200


async def test_get_booking_details(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    ok = (await book(client, a, seat["resource_id"], at(2, 9), at(2, 10))).json()
    wl = (await book(client, b, seat["resource_id"], at(2, 9), at(2, 10), waitlist=True)).json()

    g = (await client.get(f"/v1/bookings/{ok['booking_id']}", headers=a)).json()
    assert g["status"] == "CONFIRMED" and g["waitlist_position"] is None and g["expires_at"] is None
    assert [h["to_status"] for h in g["history"]] == ["CONFIRMED"]

    w = (await client.get(f"/v1/bookings/{wl['booking_id']}", headers=b)).json()
    assert w["status"] == "WAITLISTED" and w["waitlist_position"] == 1
    assert w["waitlist_id"] and w["expires_at"]
    assert (await client.get(f"/v1/bookings/{uuid.uuid4()}", headers=a)).status_code == 404


async def test_list_my_bookings(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    other, _ = await make_user(client)
    r1 = await create(client, admin, capacity=10)
    r2 = await create(client, admin, capacity=10)
    b1 = (await book(client, student, r1["resource_id"], at(2, 9), at(2, 10))).json()
    await book(client, student, r1["resource_id"], at(2, 10), at(2, 11))
    await book(client, student, r2["resource_id"], at(3, 9), at(3, 10))
    await cancel(client, student, b1["booking_id"])

    got = (await client.get("/v1/users/me/bookings", headers=student)).json()
    assert [i["start_time"][:13] for i in got["items"]] == [
        "2030-01-03T09",
        "2030-01-02T10",
        "2030-01-02T09",
    ]
    assert got["next_cursor"] is None

    p1 = (await client.get("/v1/users/me/bookings", params={"limit": 2}, headers=student)).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = (
        await client.get(
            "/v1/users/me/bookings",
            params={"limit": 2, "cursor": p1["next_cursor"]},
            headers=student,
        )
    ).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert {i["booking_id"] for i in p1["items"] + p2["items"]} == {
        i["booking_id"] for i in got["items"]
    }

    cancelled = (
        await client.get("/v1/users/me/bookings", params={"status": "CANCELLED"}, headers=student)
    ).json()
    assert [i["booking_id"] for i in cancelled["items"]] == [b1["booking_id"]]
    later = (
        await client.get(
            "/v1/users/me/bookings",
            params={"from": at(3, 0).isoformat()},
            headers=student,
        )
    ).json()
    assert len(later["items"]) == 1
    assert (await client.get("/v1/users/me/bookings", headers=other)).json()["items"] == []
    assert (
        await client.get("/v1/users/me/bookings", params={"status": "NOPE"}, headers=student)
    ).status_code == 422


async def test_force_deactivate_cancels_everything_atomically(client):
    admin, _ = await make_user(client, "admin", "staff")
    u1, _ = await make_user(client)
    u2, _ = await make_user(client)
    u3, _ = await make_user(client)
    room = await create(client, admin, capacity=2, max_quantity_per_booking=1)
    rid = uuid.UUID(room["resource_id"])
    ids = [
        (await book(client, u, rid, at(2, 9), at(2, 10), waitlist=(i == 2))).json()["booking_id"]
        for i, u in enumerate([u1, u2, u3])
    ]
    assert (
        await client.post(f"/v1/admin/resources/{rid}/deactivate", headers=u1)
    ).status_code == 403
    r = await client.post(f"/v1/admin/resources/{rid}/deactivate", headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HAS_ACTIVE_BOOKINGS"

    r = await client.post(
        f"/v1/admin/resources/{rid}/deactivate", json={"force": True}, headers=admin
    )
    assert r.status_code == 200 and r.json()["active"] is False
    rows = await fetch("SELECT status::text s FROM bookings WHERE resource_id = $1", rid)
    assert [x["s"] for x in rows] == ["CANCELLED"] * 3
    assert await total_used(rid) == 0 and await invariant_violations(rid) == 0
    assert (
        await fetchval(
            "SELECT count(*) FROM booking_status_history WHERE reason = 'resource_deactivated'"
            " AND booking_id = ANY($1)",
            [uuid.UUID(i) for i in ids],
        )
        == 3
    )
    released = await fetchval(
        "SELECT count(*) FROM outbox_events WHERE event_type = 'CapacityReleased'"
        " AND aggregate_id IN (SELECT booking_id FROM bookings WHERE resource_id = $1)",
        rid,
    )
    assert released == 0  # nobody to promote on a dead resource
    r = await book(client, u1, rid, at(3, 9), at(3, 10))
    assert r.status_code == 409 and r.json()["error"]["code"] == "RESOURCE_INACTIVE"
