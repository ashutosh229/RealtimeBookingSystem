import uuid

import pytest

from tests.integration.helpers import at, book, create, make_user
from tests.integration.test_promotion import cancel, promote


def uid(x) -> uuid.UUID:
    return uuid.UUID(str(x))


@pytest.mark.parametrize("policy,expected", [("FAIR_SHARE", "w"), ("FAIR_SHARE_Q", "p")])
async def test_contended_history_changes_the_winner(client, policy, expected):
    admin, _ = await make_user(client, "admin", "staff")
    w, _ = await make_user(client)  # won a seat after waiting in a crowded queue
    p, _ = await make_user(client)  # won a seat directly, no queue
    owner_x, _ = await make_user(client)
    owner_t, _ = await make_user(client)
    e1, _ = await make_user(client)
    e2, _ = await make_user(client)

    async def seat(**over):
        return await create(
            client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1, **over
        )

    # history for W: promoted from the head of a three-person queue, so two others still waited (contended)
    x = await seat()
    held = (await book(client, owner_x, x["resource_id"], at(2, 9), at(2, 10))).json()
    for h in (w, e1, e2):
        await book(client, h, x["resource_id"], at(2, 9), at(2, 10), waitlist=True)
    await cancel(client, owner_x, held["booking_id"])
    assert len(await promote(x["resource_id"])) == 1

    # history for P: one direct, uncontended win on another seat
    y = await seat()
    assert (await book(client, p, y["resource_id"], at(3, 9), at(3, 10))).status_code == 201

    # target seat: W queues first, P second; equal plain counts (1 each)
    t = await seat(policy_name=policy)
    held_t = (await book(client, owner_t, t["resource_id"], at(4, 9), at(4, 10))).json()
    bk_w = (await book(client, w, t["resource_id"], at(4, 9), at(4, 10), waitlist=True)).json()
    bk_p = (await book(client, p, t["resource_id"], at(4, 9), at(4, 10), waitlist=True)).json()
    await cancel(client, owner_t, held_t["booking_id"])

    winner = {"w": bk_w, "p": bk_p}[expected]
    assert await promote(t["resource_id"]) == [uid(winner["booking_id"])]
