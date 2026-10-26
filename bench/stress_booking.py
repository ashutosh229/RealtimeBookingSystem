"""Booking stress test with database-verified invariants.

Usage (API on :8080 and Postgres on :5432 published by compose; run `make seed` once first):
    python bench/stress_booking.py --levels 20 50 100 200 --repeat 3 --note "laptop, compose, 1 API replica"
Env overrides: BENCH_API, BENCH_DB_DSN, BENCH_ADMIN_EMAIL, BENCH_ADMIN_PASSWORD
"""

import argparse
import asyncio
import csv
import datetime as dt
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import asyncpg
import httpx

API = os.environ.get("BENCH_API", "http://localhost:8080/v1")
DSN = os.environ.get("BENCH_DB_DSN", "postgresql://rtbs:change_me@localhost:5432/rtbs")
ADMIN = (
    os.environ.get("BENCH_ADMIN_EMAIL", "admin@campus.test"),
    os.environ.get("BENCH_ADMIN_PASSWORD", "password123"),
)
PW = "password123"

INVARIANT_SQL = """
SELECT count(*) FROM slot_usage s
WHERE s.resource_id = $1 AND (s.used > s.capacity OR s.used <> COALESCE(
  (SELECT SUM(b.quantity) FROM bookings b WHERE b.resource_id = s.resource_id
   AND b.status IN ('CONFIRMED','COMPLETED') AND b.period @> s.slot_start), 0))
"""

RS = "(SELECT resource_id FROM resources WHERE name LIKE 'bench-%')"
BK = f"(SELECT booking_id FROM bookings WHERE resource_id IN {RS})"
US = "(SELECT user_id FROM users WHERE email LIKE '%@bench.test')"
CLEANUP_SQL = f"""
DELETE FROM outbox_events WHERE aggregate_id IN {BK};
DELETE FROM allocation_records WHERE booking_id IN {BK};
DELETE FROM booking_status_history WHERE booking_id IN {BK};
DELETE FROM waitlist_entries WHERE booking_id IN {BK};
DELETE FROM bookings WHERE resource_id IN {RS};
DELETE FROM slot_usage WHERE resource_id IN {RS};
DELETE FROM resources WHERE name LIKE 'bench-%';
DELETE FROM idempotency_keys WHERE user_id IN {US};
DELETE FROM refresh_tokens WHERE user_id IN {US};
DELETE FROM users WHERE email LIKE '%@bench.test';
"""


def pct(values: list[float], p: float) -> float:
    xs = sorted(values)
    return xs[max(0, math.ceil(p / 100 * len(xs)) - 1)]


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "nogit"


async def api_login(c: httpx.AsyncClient, email: str, password: str) -> dict:
    r = await c.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def make_users(c: httpx.AsyncClient, n: int) -> list[dict]:
    sem = asyncio.Semaphore(
        16
    )  # password hashing is CPU-heavy; do not stampede the server in setup

    async def one() -> dict:
        async with sem:
            email = f"{uuid.uuid4().hex[:12]}@bench.test"
            r = await c.post(
                "/auth/register", json={"email": email, "name": "bench", "password": PW}
            )
            r.raise_for_status()
            return await api_login(c, email, PW)

    return list(await asyncio.gather(*(one() for _ in range(n))))


async def create_resource(c: httpx.AsyncClient, admin: dict, **over) -> str:
    body = dict(
        name=f"bench-{uuid.uuid4().hex[:8]}",
        type="ROOM",
        capacity=5,
        slot_minutes=60,
        open_time="00:00",
        close_time="23:59",
        timezone="UTC",
        max_slots_per_booking=4,
        max_quantity_per_booking=1,
    )
    body.update(over)
    r = await c.post("/admin/resources", json=body, headers=admin)
    r.raise_for_status()
    return r.json()["resource_id"]


async def book(c, headers, rid, start, hours, q=1, key=None):
    body = {
        "resource_id": rid,
        "start_time": start.isoformat(),
        "end_time": (start + dt.timedelta(hours=hours)).isoformat(),
        "quantity": q,
    }
    t0 = time.perf_counter()
    try:
        r = await c.post(
            "/bookings",
            json=body,
            headers={**headers, "Idempotency-Key": key or uuid.uuid4().hex},
        )
        status, data = r.status_code, r.json()
    except httpx.HTTPError as e:
        status, data = 0, {"error": repr(e)}
    return status, time.perf_counter() - t0, data


async def fire(coros):
    t0 = time.perf_counter()
    out = await asyncio.gather(*coros)
    return out, time.perf_counter() - t0


async def sc_last_seat(c, admin, users, rng, start):
    rid = await create_resource(c, admin, type="SEAT", capacity=1)
    out, wall = await fire([book(c, h, rid, start, 1) for h in users])
    return rid, out, wall, 1


async def sc_room(c, admin, users, rng, start):
    cap = max(1, len(users) // 4)  # guarantees contention at every level
    rid = await create_resource(c, admin, capacity=cap)
    out, wall = await fire([book(c, h, rid, start, 1) for h in users])
    return rid, out, wall, cap


async def sc_idempotent(c, admin, users, rng, start):
    rid = await create_resource(c, admin, capacity=5)
    key = uuid.uuid4().hex
    out, wall = await fire([book(c, users[0], rid, start, 1, key=key) for _ in users])
    return rid, out, wall, 1


async def sc_overlap(c, admin, users, rng, start):
    rid = await create_resource(c, admin, capacity=10, max_quantity_per_booking=3)
    jobs = []
    for h in users:
        off, length, q = rng.randrange(6), rng.randint(1, 3), rng.randint(1, 3)
        jobs.append(book(c, h, rid, start + dt.timedelta(hours=off), length, q))
    out, wall = await fire(jobs)
    return rid, out, wall, None


SCENARIOS = {
    "last_seat": sc_last_seat,
    "scarce_room": sc_room,
    "idempotent_storm": sc_idempotent,
    "random_overlap": sc_overlap,
}


async def judge(pool, name, n, rep, rid, out, wall, expected) -> dict:
    statuses = Counter(s for s, _, _ in out)
    lat = [lt * 1000 for _, lt, _ in out]
    confirmed_db = await pool.fetchval(
        "SELECT count(*) FROM bookings WHERE resource_id = $1 AND status = 'CONFIRMED'",
        uuid.UUID(rid),
    )
    violations = await pool.fetchval(INVARIANT_SQL, uuid.UUID(rid))
    if name == "idempotent_storm":
        ids = {d.get("booking_id") for s, _, d in out if s == 201}
        confirmed_http = len(ids)
        ok = (
            set(statuses) == {201}
            and len(ids) == 1
            and confirmed_db == 1
            and violations == 0
        )
    else:
        confirmed_http = statuses.get(201, 0)
        ok = (
            violations == 0
            and set(statuses) <= {201, 409}
            and confirmed_db == confirmed_http
            and (expected is None or confirmed_db == expected)
        )
    return {
        "scenario": name,
        "users": n,
        "repeat": rep,
        "confirmed_http": confirmed_http,
        "confirmed_db": confirmed_db,
        "expected": expected,
        "status_counts": json.dumps(dict(statuses)),
        "p50_ms": round(pct(lat, 50), 1),
        "p95_ms": round(pct(lat, 95), 1),
        "p99_ms": round(pct(lat, 99), 1),
        "max_ms": round(max(lat), 1),
        "wall_s": round(wall, 2),
        "req_per_s": round(len(out) / wall, 1),
        "violations": violations,
        "passed": ok,
    }


async def main(args) -> int:
    out_dir = (
        Path(__file__).parent
        / "results"
        / f"{time.strftime('%Y%m%d-%H%M%S')}_{git_sha()}"
    )
    out_dir.mkdir(parents=True)
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    rows: list[dict] = []
    start = (dt.datetime.now(dt.UTC) + dt.timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    limits = httpx.Limits(max_connections=600, max_keepalive_connections=100)
    try:
        async with httpx.AsyncClient(base_url=API, timeout=120, limits=limits) as c:
            admin = await api_login(c, *ADMIN)
            warm = await make_users(c, 10)  # warm-up, discarded
            await sc_room(c, admin, warm, random.Random(0), start)
            for n in args.levels:
                users = await make_users(c, n)
                for rep in range(args.repeat):
                    for name, fn in SCENARIOS.items():
                        rng = random.Random(args.seed + n * 100 + rep)
                        rid, out, wall, expected = await fn(c, admin, users, rng, start)
                        row = await judge(pool, name, n, rep, rid, out, wall, expected)
                        rows.append(row)
                        print(
                            f"{'PASS' if row['passed'] else 'FAIL'}  {name:<17} n={n:<4} rep={rep} "
                            f"confirmed={row['confirmed_db']}/{expected} viol={row['violations']} "
                            f"p95={row['p95_ms']}ms rps={row['req_per_s']} {row['status_counts']}"
                        )
    finally:
        if not args.keep:
            await pool.execute(CLEANUP_SQL)
        await pool.close()

    with open(out_dir / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    all_ok = all(r["passed"] for r in rows)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "all_passed": all_ok,
                "runs": len(rows),
                "total_violations": sum(r["violations"] for r in rows),
                "args": vars(args),
                "note": args.note,
                "git_sha": git_sha(),
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "api": API,
                "start_slot": start.isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"\n{'ALL PASSED' if all_ok else 'FAILURES'}: {len(rows)} runs, results in {out_dir}"
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=int, nargs="+", default=[20, 50, 100])
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--keep", action="store_true", help="keep bench data in the database"
    )
    ap.add_argument("--note", default="", help="free text: hardware, replicas, config")
    sys.exit(asyncio.run(main(ap.parse_args())))
