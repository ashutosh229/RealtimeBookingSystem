import uuid

import pytest

from app.platform import db
from app.worker import promoter
from tests.integration.helpers import (
    at,
    book,
    create,
    fetch,
    fetchval,
    invariant_violations,
    make_user,
)


async def promote(rid, **kw) -> list[uuid.UUID]:
    async with db.get_pool().acquire() as conn:
        return await promoter.promote_for_resource(conn, uuid.UUID(str(rid)), **kw)


async def cancel(c, headers, bid):
    return await c.post(f"/v1/bookings/{bid}/cancel", headers=headers)


async def status(bid) -> str:
    return await fetchval("SELECT status::text FROM bookings WHERE booking_id = $1", uuid.UUID(bid))


def uid(x: str) -> uuid.UUID:
    return uuid.UUID(x)


async def test_fifo_promotes_the_head_of_the_queue(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    c, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = seat["resource_id"]
    bk_a = (await book(client, a, rid, at(2, 9), at(2, 10))).json()
    bk_b = (await book(client, b, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    bk_c = (await book(client, c, rid, at(2, 9), at(2, 10), waitlist=True)).json()

    assert await promote(rid) == []  # nothing free yet
    await cancel(client, a, bk_a["booking_id"])
    assert await promote(rid) == [uid(bk_b["booking_id"])]

    bid = uid(bk_b["booking_id"])
    assert (
        await status(bk_b["booking_id"]) == "CONFIRMED"
        and await status(bk_c["booking_id"]) == "WAITLISTED"
    )
    hist = await fetch(
        "SELECT from_status::text f, to_status::text t, reason FROM booking_status_history"
        " WHERE booking_id = $1 ORDER BY id",
        bid,
    )
    assert [(h["f"], h["t"]) for h in hist] == [
        ("REQUESTED", "WAITLISTED"),
        ("WAITLISTED", "CONFIRMED"),
    ]
    assert hist[-1]["reason"] == "promoted"
    assert (
        await fetchval(
            "SELECT inputs->>'policy' FROM allocation_records WHERE booking_id = $1"
            " AND decision_type = 'PROMOTE'",
            bid,
        )
        == "FIFO"
    )
    events = await fetch(
        "SELECT event_type FROM outbox_events WHERE aggregate_id = $1 ORDER BY id", bid
    )
    assert [e["event_type"] for e in events] == ["BookingWaitlisted", "BookingPromoted"]
    wl = await fetch(
        "SELECT status::text s, promoted_at FROM waitlist_entries WHERE booking_id = $1",
        bid,
    )
    assert wl[0]["s"] == "PROMOTED" and wl[0]["promoted_at"] is not None
    assert await fetchval(
        "SELECT confirmed_at IS NOT NULL FROM bookings WHERE booking_id = $1", bid
    )
    assert await fetchval("SELECT used FROM slot_usage WHERE resource_id = $1", uid(rid)) == 1
    assert await invariant_violations(rid) == 0
    assert await promote(rid) == []  # repeating is harmless


@pytest.mark.parametrize("policy,winner", [("FIFO", "heavy"), ("FAIR_SHARE", "light")])
async def test_policy_decides_who_is_promoted(client, policy, winner):
    admin, _ = await make_user(client, "admin", "staff")
    owner, _ = await make_user(client)
    heavy, _ = await make_user(client)
    light, _ = await make_user(client)
    seat = await create(
        client,
        admin,
        type="SEAT",
        capacity=1,
        max_quantity_per_booking=1,
        policy_name=policy,
    )
    other1 = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    other2 = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    for o in (other1, other2):  # heavy already won two seats recently
        assert (await book(client, heavy, o["resource_id"], at(2, 9), at(2, 10))).status_code == 201

    rid = seat["resource_id"]
    bk_o = (await book(client, owner, rid, at(2, 9), at(2, 10))).json()
    bk_h = (
        await book(client, heavy, rid, at(2, 9), at(2, 10), waitlist=True)
    ).json()  # queued first
    bk_l = (await book(client, light, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    await cancel(client, owner, bk_o["booking_id"])

    expected = {"heavy": bk_h, "light": bk_l}[winner]["booking_id"]
    assert await promote(rid) == [uid(expected)]
    inputs = await fetchval(
        "SELECT inputs FROM allocation_records WHERE booking_id = $1 AND decision_type = 'PROMOTE'",
        uid(expected),
    )
    assert inputs["policy"] == policy
    if policy == "FAIR_SHARE":
        assert inputs["recent_allocations"] == 0 and inputs["seq"] > 0
    assert await invariant_violations(rid) == 0


async def test_fair_share_reranks_after_each_promotion(client):
    admin, _ = await make_user(client, "admin", "staff")
    f1, _ = await make_user(client)
    f2, _ = await make_user(client)
    u, _ = await make_user(client)
    v, _ = await make_user(client)
    room = await create(
        client, admin, capacity=2, max_quantity_per_booking=1, policy_name="FAIR_SHARE"
    )
    rid = room["resource_id"]
    fill = [(await book(client, h, rid, at(2, 9), at(2, 10))).json() for h in (f1, f2)]
    u1 = (await book(client, u, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    u2 = (await book(client, u, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    v1 = (await book(client, v, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    for h, bk in zip((f1, f2), fill, strict=True):
        await cancel(client, h, bk["booking_id"])

    # u's second request would win on queue order, but u already took one slot in this pass
    assert await promote(rid) == [uid(u1["booking_id"]), uid(v1["booking_id"])]
    assert await status(u2["booking_id"]) == "WAITLISTED"
    assert await invariant_violations(rid) == 0


async def test_ineligible_candidates_are_skipped_and_recorded_once(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client, group="general")
    c, _ = await make_user(client, group="pg")
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = seat["resource_id"]
    bk_a = (await book(client, a, rid, at(2, 9), at(2, 10))).json()
    bk_b = (await book(client, b, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    bk_c = (await book(client, c, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    r = await client.patch(
        f"/v1/admin/resources/{rid}", json={"eligible_groups": ["pg"]}, headers=admin
    )
    assert r.status_code == 200  # rules tighten while b waits
    await cancel(client, a, bk_a["booking_id"])

    assert await promote(rid) == [uid(bk_c["booking_id"])]  # b is ahead in the queue but ineligible
    assert await status(bk_b["booking_id"]) == "WAITLISTED"
    assert await promote(rid) == []
    skips = await fetch(
        "SELECT reason FROM allocation_records WHERE booking_id = $1"
        " AND decision_type = 'SKIP_INELIGIBLE'",
        uid(bk_b["booking_id"]),
    )
    assert [s["reason"] for s in skips] == ["NOT_ELIGIBLE"]  # once, despite two passes
    assert await invariant_violations(rid) == 0


async def test_backfilling_versus_strict_order(client):
    admin, _ = await make_user(client, "admin", "staff")
    a1, _ = await make_user(client)
    a2, _ = await make_user(client)
    big, _ = await make_user(client)
    small, _ = await make_user(client)
    room = await create(client, admin, capacity=3, max_quantity_per_booking=3)
    rid = room["resource_id"]
    await book(client, a1, rid, at(2, 9), at(2, 10), q=2)
    bk_a2 = (await book(client, a2, rid, at(2, 9), at(2, 10), q=1)).json()  # room is now full
    bk_big = (await book(client, big, rid, at(2, 9), at(2, 10), q=3, waitlist=True)).json()
    bk_small = (await book(client, small, rid, at(2, 9), at(2, 10), q=1, waitlist=True)).json()
    await cancel(client, a2, bk_a2["booking_id"])  # one unit frees up

    assert await promote(rid, strict=True) == []  # head of line needs 3 and blocks the rest
    assert await status(bk_small["booking_id"]) == "WAITLISTED"
    assert await promote(rid) == [
        uid(bk_small["booking_id"])
    ]  # backfill: the small request goes first
    assert await status(bk_big["booking_id"]) == "WAITLISTED"
    assert await fetchval("SELECT used FROM slot_usage WHERE resource_id = $1", uid(rid)) == 3
    assert await invariant_violations(rid) == 0
