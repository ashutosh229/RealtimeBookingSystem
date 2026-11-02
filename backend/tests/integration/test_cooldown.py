from datetime import timedelta

from app.platform import clock
from app.platform.config import get_settings
from tests.integration.helpers import (
    NOW,
    at,
    book,
    create,
    fetch,
    invariant_violations,
    make_user,
)
from tests.integration.test_promotion import cancel, promote, status, uid


async def test_cooldown_blocks_back_to_back_wins_then_expires(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "promotion_min_gap_minutes", 60)
    admin, _ = await make_user(client, "admin", "staff")
    owner, _ = await make_user(client)
    u, _ = await make_user(client)
    v, _ = await make_user(client)
    seat = dict(type="SEAT", capacity=1, max_quantity_per_booking=1)
    elsewhere, target = await create(client, admin, **seat), await create(client, admin, **seat)
    rid = target["resource_id"]
    assert (await book(client, u, elsewhere["resource_id"], at(2, 9), at(2, 10))).status_code == 201

    bk_o = (await book(client, owner, rid, at(2, 9), at(2, 10))).json()
    bk_u = (await book(client, u, rid, at(2, 9), at(2, 10), waitlist=True)).json()  # queued first
    bk_v = (await book(client, v, rid, at(2, 9), at(2, 10), waitlist=True)).json()
    await cancel(client, owner, bk_o["booking_id"])

    assert await promote(rid) == [uid(bk_v["booking_id"])]  # u is cooling: v goes first
    assert await status(bk_u["booking_id"]) == "WAITLISTED"
    assert await promote(rid) == []
    skips = await fetch(
        "SELECT reason FROM allocation_records WHERE booking_id = $1"
        " AND decision_type = 'SKIP_INELIGIBLE'",
        uid(bk_u["booking_id"]),
    )
    assert [s["reason"] for s in skips] == ["COOLDOWN"]  # recorded once

    await cancel(client, v, bk_v["booking_id"])
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=61))  # the gap has passed
    assert await promote(rid) == [uid(bk_u["booking_id"])]
    assert await invariant_violations(rid) == 0
