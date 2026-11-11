import uuid

from app.platform import db
from tests.integration.helpers import make_user


async def add(user_id: str, n: int) -> list[int]:
    ids = []
    async with db.get_pool().acquire() as conn:
        for i in range(n):
            ids.append(
                await conn.fetchval(
                    "INSERT INTO notifications (user_id, type, payload, event_id) VALUES ($1, 'BookingConfirmed',"
                    " $2, $3) RETURNING id",
                    uuid.UUID(user_id),
                    {"message": f"m{i}"},
                    uuid.uuid4(),
                )
            )
    return ids


async def test_polling_with_since_and_limit(client):
    a, a_id = await make_user(client)
    b, b_id = await make_user(client)
    ids = await add(a_id, 3)
    await add(b_id, 2)
    url = "/v1/users/me/notifications"
    got = (await client.get(url, headers=a)).json()["items"]
    assert (
        [i["id"] for i in got] == ids
        and got[0]["payload"]["message"] == "m0"
        and got[0]["read_at"] is None
    )
    assert [
        i["id"]
        for i in (await client.get(url, params={"since": ids[0]}, headers=a)).json()["items"]
    ] == ids[1:]
    assert len((await client.get(url, params={"limit": 2}, headers=a)).json()["items"]) == 2
    assert (await client.get(url, params={"since": ids[-1]}, headers=a)).json()["items"] == []
    assert (await client.get(url, params={"limit": 0}, headers=a)).status_code == 422
    assert (await client.get(url)).status_code == 401


async def test_mark_read_is_owner_only_and_idempotent(client):
    a, a_id = await make_user(client)
    b, _ = await make_user(client)
    (nid,) = await add(a_id, 1)
    url = f"/v1/users/me/notifications/{nid}/read"
    assert (await client.post(url, headers=b)).status_code == 404  # someone else's id looks missing
    assert (await client.post(url, headers=a)).status_code == 204
    first = (await client.get("/v1/users/me/notifications", headers=a)).json()["items"][0][
        "read_at"
    ]
    assert first is not None
    assert (await client.post(url, headers=a)).status_code == 204
    again = (await client.get("/v1/users/me/notifications", headers=a)).json()["items"][0][
        "read_at"
    ]
    assert again == first  # the first read time is kept
    assert (
        await client.post("/v1/users/me/notifications/99999999/read", headers=a)
    ).status_code == 404
