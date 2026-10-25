import datetime as dt
import uuid

from app.platform import db

PW = "password123"
NOW = dt.datetime(
    2030, 1, 1, 9, 30, tzinfo=dt.UTC
)  # frozen "now": Jan 7 is inside the 14-day horizon


def tag() -> str:
    return uuid.uuid4().hex[:8]


def at(day: int, h: int, m: int = 0) -> dt.datetime:
    return dt.datetime(2030, 1, day, h, m, tzinfo=dt.UTC)


def new_key() -> str:
    return uuid.uuid4().hex


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


async def book(c, headers, rid, start, end, q=1, waitlist=False, k=None, path="/v1/bookings"):
    return await c.post(
        path,
        headers={**headers, "Idempotency-Key": k or new_key()},
        json={
            "resource_id": str(rid),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "quantity": q,
            "waitlist_if_full": waitlist,
        },
    )


async def fetch(sql, *args):
    async with db.get_pool().acquire() as conn:
        return await conn.fetch(sql, *args)


async def fetchval(sql, *args):
    async with db.get_pool().acquire() as conn:
        return await conn.fetchval(sql, *args)


async def invariant_violations(rid) -> int:
    """Section 31.3 invariant: ledger equals the sum of confirmed bookings, and never exceeds capacity."""
    return await fetchval(
        "SELECT count(*) FROM slot_usage s WHERE s.resource_id = $1 AND (s.used > s.capacity OR s.used <> COALESCE("
        "(SELECT SUM(b.quantity) FROM bookings b WHERE b.resource_id = s.resource_id"
        " AND b.status IN ('CONFIRMED','COMPLETED') AND b.period @> s.slot_start), 0))",
        uuid.UUID(str(rid)),
    )
