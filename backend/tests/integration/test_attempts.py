import uuid

import pytest

from app.messaging import outbox
from tests.integration.helpers import (
    at,
    book,
    create,
    fetch,
    make_user,
    new_key,
)


async def rows_of(uid_: str):
    return await fetch(
        "SELECT outcome, reason, detail, http_status, booking_id, user_group, quantity,"
        " waitlist_requested, resource_id FROM booking_attempts WHERE user_id = $1 ORDER BY id",
        uuid.UUID(uid_),
    )


async def seat(client, admin):
    return await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)


async def test_confirmed_booking_is_logged(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client, group="ug")
    s = await seat(client, admin)
    r = await book(client, student, s["resource_id"], at(2, 9), at(2, 10))
    assert r.status_code == 201
    (row,) = await rows_of(uid)
    assert (row["outcome"], row["reason"], row["detail"], row["http_status"]) == (
        "CONFIRMED",
        None,
        None,
        201,
    )
    assert str(row["booking_id"]) == r.json()["booking_id"]
    assert (row["user_group"], row["quantity"], row["waitlist_requested"]) == (
        "ug",
        1,
        False,
    )


async def test_capacity_outcomes_are_logged_with_their_detail(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, b_id = await make_user(client)
    c, c_id = await make_user(client)
    d, d_id = await make_user(client)
    s = await seat(client, admin)
    rid = s["resource_id"]
    assert (await book(client, a, rid, at(2, 9), at(2, 10))).status_code == 201
    assert (await book(client, b, rid, at(2, 9), at(2, 10))).status_code == 409
    rc = await book(client, c, rid, at(2, 9), at(2, 10), waitlist=True)
    assert rc.status_code == 202
    assert (
        await book(client, d, rid, at(2, 9), at(2, 10))
    ).status_code == 409  # a queue exists now

    (rb,), (rc_row,), (rd,) = (
        await rows_of(b_id),
        await rows_of(c_id),
        await rows_of(d_id),
    )
    assert (
        rb["outcome"],
        rb["reason"],
        rb["detail"],
        rb["http_status"],
        rb["booking_id"],
    ) == ("REJECTED", "CAPACITY_UNAVAILABLE", "full", 409, None)
    assert (
        rc_row["outcome"],
        rc_row["detail"],
        rc_row["http_status"],
        rc_row["waitlist_requested"],
    ) == ("WAITLISTED", "full", 202, True)
    assert str(rc_row["booking_id"]) == rc.json()["booking_id"]
    assert (rd["outcome"], rd["reason"], rd["detail"]) == (
        "REJECTED",
        "CAPACITY_UNAVAILABLE",
        "queue_exists",
    )


async def test_rule_rejections_are_logged_even_though_their_transaction_rolls_back(
    client,
):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client, group="general")
    room = await create(client, admin, capacity=10)
    pg = await create(client, admin, eligible_groups=["pg"])
    dead = await create(client, admin)
    await client.post(f"/v1/admin/resources/{dead['resource_id']}/deactivate", headers=admin)
    ghost = {"resource_id": str(uuid.uuid4())}
    steps = [
        (room, at(2, 7), at(2, 8), 1, 422, "OUT_OF_HOURS"),
        (room, at(2, 9, 30), at(2, 10, 30), 1, 422, "INVALID_INTERVAL"),
        (room, at(2, 9), at(2, 10), 9, 422, "QUANTITY_OUT_OF_RANGE"),
        (pg, at(2, 9), at(2, 10), 1, 403, "NOT_ELIGIBLE"),
        (dead, at(2, 9), at(2, 10), 1, 409, "RESOURCE_INACTIVE"),
        (ghost, at(2, 9), at(2, 10), 1, 404, "NOT_FOUND"),
    ]
    for res, start, end, q, status, _code in steps:
        assert (
            await book(client, student, res["resource_id"], start, end, q=q)
        ).status_code == status
    assert (
        await book(client, student, room["resource_id"], at(3, 9), at(3, 10))
    ).status_code == 201
    assert (
        await book(client, student, room["resource_id"], at(3, 10), at(3, 11))
    ).status_code == 201
    assert (
        await book(client, student, room["resource_id"], at(3, 11), at(3, 12))
    ).status_code == 409

    got = [(r["outcome"], r["reason"], r["http_status"]) for r in await rows_of(uid)]
    assert got == (
        [("REJECTED", code, status) for *_x, status, code in steps]
        + [("CONFIRMED", None, 201)] * 2
        + [("REJECTED", "USER_LIMIT_REACHED", 409)]
    )
    assert (
        str((await rows_of(uid))[5]["resource_id"]) == ghost["resource_id"]
    )  # logged even if it does not exist


async def test_replays_and_key_misuse_are_not_new_attempts(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    s = await seat(client, admin)
    k = new_key()
    assert (
        await book(client, student, s["resource_id"], at(2, 9), at(2, 10), k=k)
    ).status_code == 201
    assert (
        await book(client, student, s["resource_id"], at(2, 9), at(2, 10), k=k)
    ).status_code == 201
    other = await book(client, student, s["resource_id"], at(2, 10), at(2, 11), k=k)
    assert other.status_code == 422 and other.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(await rows_of(uid)) == 1


async def test_crash_midway_leaves_no_attempt(client, monkeypatch):
    admin, _ = await make_user(client, "admin", "staff")
    student, uid = await make_user(client)
    s = await seat(client, admin)

    async def boom(*_a, **_k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(outbox, "add", boom)
    with pytest.raises(RuntimeError):
        await book(client, student, s["resource_id"], at(2, 9), at(2, 10))
    assert await rows_of(uid) == []  # the CONFIRMED attempt rolled back with the booking


async def test_admin_attempt_listing(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, b_id = await make_user(client)
    c, _ = await make_user(client)
    s = await seat(client, admin)
    rid = s["resource_id"]
    for h in (a, b, c):
        await book(client, h, rid, at(2, 9), at(2, 10))
    url = "/v1/admin/attempts"
    assert (await client.get(url, headers=a)).status_code == 403
    allr = (await client.get(url, params={"resource_id": rid}, headers=admin)).json()["items"]
    assert [i["outcome"] for i in allr] == [
        "REJECTED",
        "REJECTED",
        "CONFIRMED",
    ]  # newest first
    rej = (
        await client.get(url, params={"resource_id": rid, "outcome": "REJECTED"}, headers=admin)
    ).json()
    assert len(rej["items"]) == 2 and all(
        i["reason"] == "CAPACITY_UNAVAILABLE" for i in rej["items"]
    )
    mine = (await client.get(url, params={"user_id": b_id}, headers=admin)).json()["items"]
    assert len(mine) == 1 and mine[0]["user_group"] == "general"
    p1 = (await client.get(url, params={"resource_id": rid, "limit": 2}, headers=admin)).json()
    p2 = (
        await client.get(
            url,
            params={"resource_id": rid, "limit": 2, "cursor": p1["next_cursor"]},
            headers=admin,
        )
    ).json()
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert [i["id"] for i in p1["items"] + p2["items"]] == [i["id"] for i in allr]
    assert (await client.get(url, params={"cursor": "garbage"}, headers=admin)).status_code == 422
    assert (await client.get(url, params={"outcome": "NOPE"}, headers=admin)).status_code == 422


async def test_rejection_summary(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    c, _ = await make_user(client)
    d, _ = await make_user(client)
    s = await seat(client, admin)
    rid = s["resource_id"]
    await book(client, a, rid, at(2, 9), at(2, 10))
    await book(client, b, rid, at(2, 9), at(2, 10))
    await book(client, c, rid, at(2, 9), at(2, 10), waitlist=True)
    await book(client, d, rid, at(2, 9), at(2, 10))
    url = "/v1/admin/metrics/rejections"
    assert (await client.get(url, headers=a)).status_code == 403
    m = (await client.get(url, params={"resource_id": rid}, headers=admin)).json()
    assert (m["attempts"], m["confirmed"], m["waitlisted"], m["rejected"]) == (
        4,
        1,
        1,
        2,
    )
    assert m["rejection_rate"] == pytest.approx(0.5) and m["users_rejected"] == 2
    assert m["by_reason"] == {"CAPACITY_UNAVAILABLE": 2}
    assert m["by_group"] == [
        {"user_group": "general", "attempts": 4, "rejected": 2, "rejection_rate": 0.5}
    ]
    assert len(m["by_hour_utc"]) == 24 and m["by_hour_utc"][9] == 2 and sum(m["by_hour_utc"]) == 2
    for bad in (0, 91):
        assert (
            await client.get(url, params={"window_days": bad}, headers=admin)
        ).status_code == 422


async def test_live_jain_now_counts_users_who_were_always_rejected(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    s = await seat(client, admin)
    await book(client, a, s["resource_id"], at(2, 9), at(2, 10))
    await book(client, b, s["resource_id"], at(2, 9), at(2, 10))  # rejected, leaves no booking row
    m = (
        await client.get(
            "/v1/admin/metrics/summary",
            params={"resource_id": s["resource_id"]},
            headers=admin,
        )
    ).json()
    assert m["jain_index"] == pytest.approx(0.5)  # (1+0)^2 / (2 * 1): before C1 this read 1.0
