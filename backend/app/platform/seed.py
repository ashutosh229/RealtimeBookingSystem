"""Dev seed data. Idempotent: safe to run repeatedly. NOT for production."""

import asyncio
import datetime as dt
import os

import asyncpg
from argon2 import PasswordHasher

DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
TZ = os.environ.get("CAMPUS_TZ", "UTC")
DEV_PASSWORD = "password123"

USERS = [("admin@campus.test", "Admin", "admin", "staff")] + [
    (f"student{i}@campus.test", f"Student {i}", "student", "ug" if i <= 3 else "pg")
    for i in range(1, 6)
]

OPEN, CLOSE = dt.time(8, 0), dt.time(22, 0)

RESOURCES = [
    dict(
        name=f"Library Seat A{i}",
        type="SEAT",
        capacity=1,
        slot=60,
        max_slots=4,
        max_qty=1,
        groups=[],
    )
    for i in range(1, 11)
] + [
    dict(
        name="Study Room 1",
        type="ROOM",
        capacity=6,
        slot=60,
        max_slots=3,
        max_qty=4,
        groups=[],
    ),
    dict(
        name="CSE Lab",
        type="ROOM",
        capacity=20,
        slot=60,
        max_slots=3,
        max_qty=5,
        groups=["ug", "pg", "faculty"],
    ),
    dict(
        name="GPU Cluster Pool",
        type="COMPUTE_POOL",
        capacity=64,
        slot=60,
        max_slots=4,
        max_qty=16,
        groups=["pg", "faculty"],
    ),
]


async def main() -> None:
    ph = PasswordHasher()
    pw_hash = ph.hash(DEV_PASSWORD)
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            for email, name, role, group in USERS:
                await conn.execute(
                    "INSERT INTO users (email, name, password_hash, role, user_group)"
                    " VALUES ($1, $2, $3, $4::user_role, $5) ON CONFLICT (email) DO NOTHING",
                    email,
                    name,
                    pw_hash,
                    role,
                    group,
                )
            for r in RESOURCES:
                rid = await conn.fetchval(
                    "SELECT resource_id FROM resources WHERE name = $1", r["name"]
                )
                if rid is None:
                    rid = await conn.fetchval(
                        "INSERT INTO resources (type, name, capacity, slot_minutes, open_time,"
                        " close_time, timezone, max_slots_per_booking, max_quantity_per_booking)"
                        " VALUES ($1::resource_type, $2, $3, $4, $5, $6, $7, $8, $9)"
                        " RETURNING resource_id",
                        r["type"],
                        r["name"],
                        r["capacity"],
                        r["slot"],
                        OPEN,
                        CLOSE,
                        TZ,
                        r["max_slots"],
                        r["max_qty"],
                    )
                for g in r["groups"]:
                    await conn.execute(
                        "INSERT INTO resource_eligibility (resource_id, user_group)"
                        " VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        rid,
                        g,
                    )
        print(
            f"seeded {len(USERS)} users and {len(RESOURCES)} resources (password: {DEV_PASSWORD})"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
