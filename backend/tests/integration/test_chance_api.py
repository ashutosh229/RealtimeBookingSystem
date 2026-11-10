import pytest

from tests.integration.helpers import at, book, create, make_user


async def test_chance_endpoints(client):
    admin, _ = await make_user(client, "admin", "staff")
    a, _ = await make_user(client)
    b, _ = await make_user(client)
    c, _ = await make_user(client)
    nobody, _ = await make_user(client)
    seat = await create(client, admin, type="SEAT", capacity=1, max_quantity_per_booking=1)
    rid = seat["resource_id"]
    for h in (a, b, c):  # one seat: a is confirmed, b and c are rejected
        await book(client, h, rid, at(2, 9), at(2, 10))

    url = "/v1/admin/metrics/chance"
    assert (await client.get(url, headers=a)).status_code == 403
    m = (await client.get(url, params={"resource_id": rid}, headers=admin)).json()
    assert (m["users"], m["attempts"]) == (3, 3)
    assert m["chance_mean"] == pytest.approx(1 / 3) and m["chance_min"] == 0.0
    assert m["chance_gini"] == pytest.approx(2 / 3) and m["chance_low_share"] == pytest.approx(
        2 / 3
    )
    assert m["histogram"] == [2, 0, 0, 0, 0, 0, 0, 0, 0, 1]
    (g,) = m["by_group"]
    assert (g["user_group"], g["users"]) == ("general", 3) and g["mean_chance"] == pytest.approx(
        1 / 3
    )
    for bad in (0, 91):
        assert (
            await client.get(url, params={"window_days": bad}, headers=admin)
        ).status_code == 422

    mine = (await client.get("/v1/users/me/chance", headers=a)).json()
    assert (mine["attempts"], mine["successes"], mine["my_chance"]) == (1, 1, 1.0)
    assert mine["cohort_users"] >= 3
    lost = (await client.get("/v1/users/me/chance", headers=b)).json()
    assert (lost["attempts"], lost["successes"], lost["my_chance"]) == (1, 0, 0.0)
    none = (await client.get("/v1/users/me/chance", headers=nobody)).json()
    assert (none["attempts"], none["my_chance"]) == (0, None)
    assert (await client.get("/v1/users/me/chance")).status_code == 401
