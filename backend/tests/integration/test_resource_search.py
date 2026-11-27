"""GET /resources: radius search (O7, haversine without PostGIS) and the free-window filter."""

from tests.integration.helpers import at, book, create, make_user, tag

# A spot far from any other test data, so only this file's resources fall inside the radius.
LAT, LON = -45.0, 170.0


async def search(client, headers, **params):
    return await client.get("/v1/resources", params=params, headers=headers)


async def test_radius_search_filters_and_orders_by_distance(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    t = tag()
    here = await create(client, admin, name=f"itest-geo-here-{t}", lat=LAT, lon=LON)
    near = await create(client, admin, name=f"itest-geo-near-{t}", lat=LAT + 0.0045, lon=LON)
    await create(client, admin, name=f"itest-geo-far-{t}", lat=LAT + 0.045, lon=LON)  # ~5 km
    await create(client, admin, name=f"itest-geo-none-{t}")  # no coordinates

    r = await search(client, student, lat=LAT, lon=LON, radius_m=1000)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["resource_id"] for i in items] == [here["resource_id"], near["resource_id"]]
    assert items[0]["distance_m"] < 1
    assert 450 < items[1]["distance_m"] < 550  # 0.0045 degrees of latitude is about 500 m
    assert r.json()["next_cursor"] is None

    wide = (await search(client, student, lat=LAT, lon=LON, radius_m=10000)).json()["items"]
    assert len(wide) == 3

    plain = (await search(client, student, q=f"itest-geo-here-{t}")).json()["items"]
    assert plain[0]["distance_m"] is None  # only radius searches carry a distance


async def test_radius_search_validation(client):
    student, _ = await make_user(client)
    assert (await search(client, student, lat=LAT, lon=LON)).status_code == 422
    assert (await search(client, student, lat=91, lon=LON, radius_m=100)).status_code == 422
    assert (await search(client, student, lat=LAT, lon=LON, radius_m=60000)).status_code == 422


async def test_free_window_hides_resources_full_in_that_window(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    t = tag()
    full = await create(
        client, admin, name=f"itest-win-full-{t}", capacity=1, max_quantity_per_booking=1
    )
    free = await create(
        client, admin, name=f"itest-win-free-{t}", capacity=1, max_quantity_per_booking=1
    )
    assert (
        await book(client, student, full["resource_id"], at(2, 9), at(2, 10))
    ).status_code == 201

    async def names(lo, hi):
        r = await search(
            client,
            student,
            q="itest-win-",
            available_from=lo.isoformat(),
            available_to=hi.isoformat(),
            limit=100,
        )
        assert r.status_code == 200
        return {i["name"] for i in r.json()["items"] if i["name"].endswith(t)}

    assert await names(at(2, 9, 30), at(2, 9, 45)) == {free["name"]}  # inside the full slot
    assert await names(at(2, 8), at(2, 11)) == {free["name"]}  # overlaps it
    assert await names(at(2, 10), at(2, 11)) == {
        full["name"],
        free["name"],
    }  # half-open: 10:00 is free
    assert await names(at(2, 8), at(2, 9)) == {full["name"], free["name"]}


async def test_free_window_validation(client):
    student, _ = await make_user(client)
    assert (await search(client, student, available_from=at(2, 9).isoformat())).status_code == 422
    bad = dict(available_from=at(2, 10).isoformat(), available_to=at(2, 9).isoformat())
    assert (await search(client, student, **bad)).status_code == 422
