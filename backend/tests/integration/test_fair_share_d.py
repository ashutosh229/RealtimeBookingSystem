import uuid
from datetime import timedelta

import pytest

from app.platform import clock
from tests.integration.helpers import NOW, at, book, create, make_user
from tests.integration.test_promotion import cancel, promote


def uid(x) -> uuid.UUID:
    return uuid.UUID(str(x))


@pytest.mark.parametrize("policy,expected", [("FAIR_SHARE", "w"), ("FAIR_SHARE_D", "p")])
async def test_old_history_decays_so_the_older_winner_goes_first(
    client, monkeypatch, policy, expected
):
    admin, _ = await make_user(client, "admin", "staff")
    w, _ = await make_user(client)  # won a seat just now
    p, _ = await make_user(client)  # won a seat ten days ago, same plain count
    owner, _ = await make_user(client)

    async def seat(**over):
        return await create(
            client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1, **over
        )

    x, y, target = await seat(), await seat(), await seat(policy_name=policy)

    monkeypatch.setattr(clock, "now", lambda: NOW - timedelta(days=10))
    assert (await book(client, p, y["resource_id"], at(3, 9), at(3, 10))).status_code == 201
    monkeypatch.setattr(clock, "now", lambda: NOW)
    assert (await book(client, w, x["resource_id"], at(3, 9), at(3, 10))).status_code == 201

    rid = target["resource_id"]
    held = (await book(client, owner, rid, at(4, 9), at(4, 10))).json()
    bk_w = (await book(client, w, rid, at(4, 9), at(4, 10), waitlist=True)).json()  # queued first
    bk_p = (await book(client, p, rid, at(4, 9), at(4, 10), waitlist=True)).json()
    await cancel(client, owner, held["booking_id"])

    winner = {"w": bk_w, "p": bk_p}[expected]
    assert await promote(rid) == [uid(winner["booking_id"])]
