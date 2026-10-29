import uuid
from datetime import timedelta

import pytest

from app.platform import clock
from tests.integration.helpers import NOW, at, book, create, make_user
from tests.integration.test_promotion import cancel, promote


async def get_entry(c, headers, wid):
    return await c.get(f"/v1/waitlists/{wid}", headers=headers)


async def seat_queue(client, policy="FIFO"):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    c, _ = await make_user(client)
    seat = await create(
        client,
        admin,
        type="SEAT",
        capacity=1,
        max_quantity_per_booking=1,
        policy_name=policy,
    )
    rid = seat["resource_id"]
    bk_a = (await book(client, a, rid, at(2, 9), at(2, 10))).json()
    bk_b = (await book(client, b, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    bk_c = (await book(client, c, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    return dict(admin=admin, a=a, b=b, c=c, rid=rid, bk_a=bk_a, bk_b=bk_b, bk_c=bk_c)


async def test_waitlist_entry_view_and_access(client):
    s = await seat_queue(client)
    outsider, _ = await make_user(client)
    wb, wc = s["bk_b"]["waitlist_id"], s["bk_c"]["waitlist_id"]
    body = (await get_entry(client, s["b"], wb)).json()
    assert (body["status"], body["position"], body["position_is_estimate"]) == (
        "ACTIVE",
        1,
        False,
    )
    assert body["booking_id"] == s["bk_b"]["booking_id"] and body["resource_id"] == s["rid"]
    assert (await get_entry(client, s["c"], wc)).json()["position"] == 2
    assert (await get_entry(client, outsider, wb)).status_code == 404
    assert (await get_entry(client, s["admin"], wb)).status_code == 200
    assert (await get_entry(client, s["b"], str(uuid.uuid4()))).status_code == 404

    await cancel(client, s["a"], s["bk_a"]["booking_id"])
    await promote(s["rid"])
    after = (await get_entry(client, s["b"], wb)).json()
    assert after["status"] == "PROMOTED" and after["position"] is None
    assert (await get_entry(client, s["c"], wc)).json()["position"] == 1


async def test_fair_share_position_is_flagged_as_estimate(client):
    s = await seat_queue(client, policy="FAIR_SHARE")
    body = (await get_entry(client, s["b"], s["bk_b"]["waitlist_id"])).json()
    assert body["position"] == 1 and body["position_is_estimate"] is True


async def test_admin_waitlists_listing(client):
    s = await seat_queue(client)
    url = "/v1/admin/waitlists"
    assert (await client.get(url, headers=s["b"])).status_code == 403
    p = {"resource_id": s["rid"], "limit": 1}
    p1 = (await client.get(url, params=p, headers=s["admin"])).json()
    assert [i["booking_id"] for i in p1["items"]] == [s["bk_b"]["booking_id"]] and p1["next_cursor"]
    p2 = (
        await client.get(url, params={**p, "cursor": p1["next_cursor"]}, headers=s["admin"])
    ).json()
    assert [i["booking_id"] for i in p2["items"]] == [s["bk_c"]["booking_id"]] and p2[
        "next_cursor"
    ] is None
    await cancel(client, s["b"], s["bk_b"]["booking_id"])
    rest = (await client.get(url, params={"resource_id": s["rid"]}, headers=s["admin"])).json()
    assert [i["booking_id"] for i in rest["items"]] == [
        s["bk_c"]["booking_id"]
    ]  # only ACTIVE entries
    assert (
        await client.get(url, params={"cursor": "garbage"}, headers=s["admin"])
    ).status_code == 422


async def test_admin_allocations_listing(client):
    s = await seat_queue(client)
    await cancel(client, s["a"], s["bk_a"]["booking_id"])
    await promote(s["rid"])
    url, q = "/v1/admin/allocations", {"resource_id": s["rid"]}
    assert (await client.get(url, params=q, headers=s["b"])).status_code == 403
    items = (await client.get(url, params=q, headers=s["admin"])).json()["items"]
    assert [i["decision_type"] for i in items] == [
        "PROMOTE",
        "REJECT_FULL",
        "REJECT_FULL",
        "ADMIT",
    ]
    top = items[0]
    assert top["booking_id"] == s["bk_b"]["booking_id"] and top["inputs"]["policy"] == "FIFO"
    assert (top["policy_name"], top["policy_version"]) == ("FIFO", "1.0")

    p1 = (await client.get(url, params={**q, "limit": 3}, headers=s["admin"])).json()
    assert len(p1["items"]) == 3 and p1["next_cursor"]
    p2 = (
        await client.get(
            url,
            params={**q, "limit": 3, "cursor": p1["next_cursor"]},
            headers=s["admin"],
        )
    ).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert [i["id"] for i in p1["items"] + p2["items"]] == [i["id"] for i in items]

    since = (
        await client.get(url, params={**q, "from": "2000-01-01T00:00:00Z"}, headers=s["admin"])
    ).json()
    assert len(since["items"]) == 4
    before = (
        await client.get(url, params={**q, "to": "2000-01-01T00:00:00Z"}, headers=s["admin"])
    ).json()
    assert before["items"] == []


async def test_metrics_utilization(client, monkeypatch):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    room = await create(client, admin, capacity=5, max_quantity_per_booking=3)
    assert (
        await book(client, student, room["resource_id"], at(2, 9), at(2, 11), q=2)
    ).status_code == 201
    monkeypatch.setattr(clock, "now", lambda: at(3, 0))
    m = (
        await client.get(
            "/v1/admin/metrics/summary",
            params={"resource_id": room["resource_id"], "window_days": 2},
            headers=admin,
        )
    ).json()
    # window Jan 1 00:00 to Jan 3 00:00 = 28 started slots x capacity 5 = 140 units; 2 units x 2 slots used
    assert m["utilization"] == pytest.approx(4 / 140)
    assert m["window_days"] == 2 and m["jain_index"] == 1.0 and m["waitlist_length"] == 0


async def test_metrics_fairness_waits_and_queue(client, monkeypatch):
    s = await seat_queue(client)
    await cancel(client, s["a"], s["bk_a"]["booking_id"])
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(hours=1))
    assert len(await promote(s["rid"])) == 1  # b waited one hour; c is still queued
    m = (
        await client.get(
            "/v1/admin/metrics/summary",
            params={"resource_id": s["rid"]},
            headers=s["admin"],
        )
    ).json()
    assert m["jain_index"] == pytest.approx(4 / 6)  # allocations a=1, b=1, c=0
    assert m["waitlist_length"] == 1
    assert m["wait_seconds"] == {
        "mean": 1800.0,
        "p95": 3600.0,
        "max": 3600.0,
    }  # a waited 0, b waited 3600


async def test_metrics_empty_and_validation(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    room = await create(client, admin)
    url = "/v1/admin/metrics/summary"
    m = (await client.get(url, params={"resource_id": room["resource_id"]}, headers=admin)).json()
    assert (m["utilization"], m["jain_index"], m["waitlist_length"]) == (0.0, 1.0, 0)
    assert m["wait_seconds"] == {"mean": 0.0, "p95": 0.0, "max": 0.0}
    assert (await client.get(url, headers=student)).status_code == 403
    for bad in (0, 91):
        assert (
            await client.get(url, params={"window_days": bad}, headers=admin)
        ).status_code == 422
