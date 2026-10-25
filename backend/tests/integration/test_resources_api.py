import datetime as dt
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.platform import db

PW = "password123"
DAY = "2030-01-07"


def tag() -> str:
    return uuid.uuid4().hex[:8]


@pytest_asyncio.fixture
async def client():
    try:
        await db.init_pool()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database not reachable: {e}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    async with db.get_pool().acquire() as conn:
        rs = "(SELECT resource_id FROM resources WHERE name LIKE 'itest-%')"
        await conn.execute(f"DELETE FROM bookings WHERE resource_id IN {rs}")
        await conn.execute(f"DELETE FROM slot_usage WHERE resource_id IN {rs}")
        await conn.execute("DELETE FROM resources WHERE name LIKE 'itest-%'")
        await conn.execute(
            "DELETE FROM refresh_tokens WHERE user_id IN"
            " (SELECT user_id FROM users WHERE email LIKE '%@itest.local')"
        )
        await conn.execute("DELETE FROM users WHERE email LIKE '%@itest.local'")
    await db.close_pool()


async def make_user(c, role="student", group="general"):
    email = f"{tag()}@itest.local"
    await c.post("/v1/auth/register", json={"email": email, "name": "T", "password": PW})
    async with db.get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET role = $2::user_role, user_group = $3 WHERE email = $1",
            email,
            role,
            group,
        )
    token = (await c.post("/v1/auth/login", json={"email": email, "password": PW})).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    uid = (await c.get("/v1/users/me", headers=headers)).json()["user_id"]
    return headers, uid


def payload(**over):
    base = dict(
        name=f"itest-{tag()}",
        type="ROOM",
        capacity=5,
        slot_minutes=60,
        open_time="08:00",
        close_time="22:00",
        timezone="UTC",
        max_slots_per_booking=4,
        max_quantity_per_booking=3,
    )
    return {**base, **over}


async def create(c, admin, **over):
    r = await c.post("/v1/admin/resources", json=payload(**over), headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


async def test_requires_auth(client):
    assert (await client.get("/v1/resources")).status_code == 401


async def test_admin_create_and_student_forbidden(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    res = await create(client, admin)
    assert res["open_time"] == "08:00" and res["active"] and res["eligible_groups"] == []
    r = await client.post("/v1/admin/resources", json=payload(), headers=student)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    "over",
    [
        dict(type="SEAT", capacity=2, max_quantity_per_booking=1),
        dict(open_time="22:00", close_time="08:00"),
        dict(timezone="Not/AZone"),
        dict(max_quantity_per_booking=9),
        dict(slot_minutes=45),
    ],
)
async def test_create_validation(client, over):
    admin, _ = await make_user(client, "admin", "staff")
    r = await client.post("/v1/admin/resources", json=payload(**over), headers=admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_get_resource_and_404(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    res = await create(client, admin)
    assert (
        await client.get(f"/v1/resources/{res['resource_id']}", headers=student)
    ).status_code == 200
    r = await client.get(f"/v1/resources/{uuid.uuid4()}", headers=student)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_list_filters_and_pagination(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    t = tag()
    for letter in "abc":
        await create(client, admin, name=f"itest-pg-{t}-{letter}")
    seen, cursor = [], None
    for _ in range(5):
        params = {
            "q": f"itest-pg-{t}",
            "limit": 2,
            **({"cursor": cursor} if cursor else {}),
        }
        body = (await client.get("/v1/resources", params=params, headers=student)).json()
        seen += [i["name"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert seen == [f"itest-pg-{t}-{x}" for x in "abc"]
    only_seats = (
        await client.get(
            "/v1/resources",
            params={"type": "SEAT", "q": f"itest-pg-{t}"},
            headers=student,
        )
    ).json()
    assert only_seats["items"] == []


async def test_eligibility_filter(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client, group="general")
    t = tag()
    res = await create(client, admin, name=f"itest-elig-{t}", eligible_groups=["pg"])
    assert res["eligible_groups"] == ["pg"]
    q = {"q": f"itest-elig-{t}"}
    assert (await client.get("/v1/resources", params=q, headers=student)).json()["items"] == []
    shown = (
        await client.get("/v1/resources", params={**q, "eligible_only": "false"}, headers=student)
    ).json()
    assert len(shown["items"]) == 1


async def test_availability_reads_the_ledger(client):
    admin, _ = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    res = await create(client, admin, capacity=5)
    async with db.get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO slot_usage (resource_id, slot_start, used, capacity) VALUES ($1, $2, 2, 5)",
            uuid.UUID(res["resource_id"]),
            dt.datetime(2030, 1, 7, 9, tzinfo=dt.UTC),
        )
    r = await client.get(
        f"/v1/resources/{res['resource_id']}/availability",
        params={"date": DAY},
        headers=student,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["slots"]) == 14 and body["as_of"]
    by_start = {s["start_time"][:13]: s for s in body["slots"]}
    assert by_start["2030-01-07T09"]["available"] == 3
    assert (
        by_start["2030-01-07T10"]["available"] == 5 and by_start["2030-01-07T10"]["capacity"] == 5
    )


async def test_availability_param_errors(client):
    admin, _ = await make_user(client, "admin", "staff")
    res = await create(client, admin)
    url = f"/v1/resources/{res['resource_id']}/availability"
    assert (await client.get(url, headers=admin)).status_code == 422
    assert (
        await client.get(
            f"/v1/resources/{uuid.uuid4()}/availability",
            params={"date": DAY},
            headers=admin,
        )
    ).status_code == 404


async def test_patch_capacity_rules(client):
    admin, _ = await make_user(client, "admin", "staff")
    res = await create(client, admin, capacity=5, max_quantity_per_booking=1)
    rid = res["resource_id"]
    async with db.get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO slot_usage (resource_id, slot_start, used, capacity) VALUES ($1, $2, 3, 5)",
            uuid.UUID(rid),
            dt.datetime(2030, 1, 7, 9, tzinfo=dt.UTC),
        )
    r = await client.patch(f"/v1/admin/resources/{rid}", json={"capacity": 2}, headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CAPACITY_UNAVAILABLE"
    r = await client.patch(f"/v1/admin/resources/{rid}", json={"capacity": 4}, headers=admin)
    assert r.status_code == 200 and r.json()["capacity"] == 4
    async with db.get_pool().acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT capacity FROM slot_usage WHERE resource_id = $1", uuid.UUID(rid)
            )
            == 4
        )
    r = await client.patch(
        f"/v1/admin/resources/{rid}",
        json={"max_quantity_per_booking": 9},
        headers=admin,
    )
    assert r.status_code == 422
    r = await client.patch(
        f"/v1/admin/resources/{rid}",
        json={"capacity": 1, "max_quantity_per_booking": 3},
        headers=admin,
    )
    assert r.status_code == 422


async def test_deactivate_rules(client):
    admin, admin_id = await make_user(client, "admin", "staff")
    student, _ = await make_user(client)
    busy, idle = await create(client, admin), await create(client, admin)
    async with db.get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO bookings (user_id, resource_id, start_time, end_time, quantity, status,"
            " is_exclusive, idempotency_key, request_hash)"
            " VALUES ($1, $2, '2030-01-07T09:00Z', '2030-01-07T10:00Z', 1, 'CONFIRMED', false, 'itest-key-0001', 'h')",
            uuid.UUID(admin_id),
            uuid.UUID(busy["resource_id"]),
        )
    r = await client.post(f"/v1/admin/resources/{busy['resource_id']}/deactivate", headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HAS_ACTIVE_BOOKINGS"
    r = await client.post(
        f"/v1/admin/resources/{idle['resource_id']}/deactivate",
        json={"force": True},
        headers=admin,
    )
    assert r.status_code == 501
    r = await client.post(f"/v1/admin/resources/{idle['resource_id']}/deactivate", headers=admin)
    assert r.status_code == 200 and r.json()["active"] is False
    assert (
        await client.get(f"/v1/resources/{idle['resource_id']}", headers=student)
    ).status_code == 404
    assert (
        await client.get(f"/v1/resources/{idle['resource_id']}", headers=admin)
    ).status_code == 200
