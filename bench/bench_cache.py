"""E2: availability cache on vs off under a mixed read/write workload (same server, per-request switch).

    python bench/bench_cache.py --workers 40 --duration 20 --read-ratios 0.95 0.8 0.5 --note "laptop, compose, 1 API replica"
Needs: stack up, migration applied, `make seed` done, API connected to Redis.
Cache 'off' sends Cache-Control: no-cache on every read, so it measures the uncached path on the same data.
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
RS = "(SELECT resource_id FROM resources WHERE name LIKE 'bench-cache-%')"
BK = f"(SELECT booking_id FROM bookings WHERE resource_id IN {RS})"
US = "(SELECT user_id FROM users WHERE email LIKE '%@benchcache.test')"
CLEANUP_SQL = f"""
DELETE FROM processed_events WHERE event_id IN (SELECT event_id FROM outbox_events WHERE aggregate_id IN {BK} OR aggregate_id IN {RS});
DELETE FROM outbox_events WHERE aggregate_id IN {BK} OR aggregate_id IN {RS};
DELETE FROM allocation_records WHERE booking_id IN {BK};
DELETE FROM booking_status_history WHERE booking_id IN {BK};
DELETE FROM waitlist_entries WHERE booking_id IN {BK};
DELETE FROM bookings WHERE resource_id IN {RS};
DELETE FROM slot_usage WHERE resource_id IN {RS};
DELETE FROM resources WHERE name LIKE 'bench-cache-%';
DELETE FROM notifications WHERE user_id IN {US};
DELETE FROM idempotency_keys WHERE user_id IN {US};
DELETE FROM refresh_tokens WHERE user_id IN {US};
DELETE FROM users WHERE email LIKE '%@benchcache.test';
"""


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "nogit"


def pct(values: list[float], p: float) -> float:
    xs = sorted(values)
    return xs[max(0, math.ceil(p / 100 * len(xs)) - 1)] if xs else 0.0


async def login(c, email, password) -> dict:
    r = await c.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def make_users(c, n) -> list[dict]:
    sem = asyncio.Semaphore(16)

    async def one():
        async with sem:
            email = f"{uuid.uuid4().hex[:12]}@benchcache.test"
            (
                await c.post(
                    "/auth/register", json={"email": email, "name": "b", "password": PW}
                )
            ).raise_for_status()
            return await login(c, email, PW)

    return list(await asyncio.gather(*(one() for _ in range(n))))


async def create_room(c, admin) -> str:
    r = await c.post(
        "/admin/resources",
        headers=admin,
        json=dict(
            name=f"bench-cache-{uuid.uuid4().hex[:8]}",
            type="ROOM",
            capacity=1000,
            slot_minutes=60,
            open_time="00:00",
            close_time="23:59",
            timezone="UTC",
            max_slots_per_booking=4,
            max_quantity_per_booking=1,
        ),
    )
    r.raise_for_status()
    return r.json()["resource_id"]


async def available(c, headers, rid, start, fresh) -> int | None:
    h = {**headers, **({"Cache-Control": "no-cache"} if fresh else {})}
    r = await c.get(
        f"/resources/{rid}/availability",
        params={"date": start.date().isoformat()},
        headers=h,
    )
    if r.status_code != 200:
        return None
    key = start.strftime("%Y-%m-%dT%H")
    return next(
        (s["available"] for s in r.json()["slots"] if s["start_time"][:13] == key), None
    )


async def worker(
    i, c, headers, own, rids, days, ratio, mode, t_end, t_warm, seed, out
) -> None:
    rng, n, off = random.Random(seed * 1000 + i), 0, mode == "off"

    def h(fresh=False):
        return {**headers, **({"Cache-Control": "no-cache"} if (off or fresh) else {})}

    while time.perf_counter() < t_end:
        n += 1
        measured = time.perf_counter() >= t_warm
        if rng.random() < ratio:
            rid, day = rng.choice(rids), rng.choice(days)
            t0 = time.perf_counter()
            try:
                r = await c.get(
                    f"/resources/{rid}/availability",
                    params={"date": day.isoformat()},
                    headers=h(),
                )
                status, xc = r.status_code, r.headers.get("X-Cache", "")
            except httpx.HTTPError:
                status, xc = 0, ""
            if measured:
                out["read"].append(((time.perf_counter() - t0) * 1000, status, xc))
            continue
        day = days[n % len(days)]
        start = dt.datetime(day.year, day.month, day.day, 9 + n % 10, tzinfo=dt.UTC)
        base = await available(
            c, headers, own, start, fresh=True
        )  # ground truth from the database
        t0 = time.perf_counter()
        try:
            r = await c.post(
                "/bookings",
                headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
                json={
                    "resource_id": own,
                    "start_time": start.isoformat(),
                    "end_time": (start + dt.timedelta(hours=1)).isoformat(),
                    "quantity": 1,
                },
            )
            status = r.status_code
        except httpx.HTTPError:
            status = 0
        if measured:
            out["write_book"].append(((time.perf_counter() - t0) * 1000, status))
        if status != 201 or base is None:
            continue
        a1 = await available(
            c, headers, own, start, fresh=off
        )  # read-your-write check, normal path
        t0 = time.perf_counter()
        cr = await c.post(f"/bookings/{r.json()['booking_id']}/cancel", headers=headers)
        if measured:
            out["write_cancel"].append(
                ((time.perf_counter() - t0) * 1000, cr.status_code)
            )
        a2 = await available(c, headers, own, start, fresh=off)
        if measured:
            out["checks"] += 2
            out["stale"] += int(a1 != base - 1) + int(a2 != base)


def summarize(a, ratio, mode, out) -> dict:
    ok = [ms for ms, st, _ in out["read"] if st == 200]
    hits = sum(1 for _, st, xc in out["read"] if st == 200 and xc == "HIT")
    ops = len(out["read"]) + len(out["write_book"]) + len(out["write_cancel"])
    return {
        "read_ratio": ratio,
        "cache": mode,
        "workers": a.workers,
        "duration_s": a.duration,
        "reads": len(out["read"]),
        "read_errors": len(out["read"]) - len(ok),
        "reads_per_s": round(len(out["read"]) / a.duration, 1),
        "ops_per_s": round(ops / a.duration, 1),
        "p50_ms": round(pct(ok, 50), 1),
        "p95_ms": round(pct(ok, 95), 1),
        "p99_ms": round(pct(ok, 99), 1),
        "hit_rate": round(hits / len(ok), 3) if ok else 0.0,
        "writes": len(out["write_book"]),
        "stale_checks": out["checks"],
        "stale": out["stale"],
    }


async def main(a) -> int:
    out_dir = (
        Path(__file__).parent
        / "results"
        / f"cache-{time.strftime('%Y%m%d-%H%M%S')}_{git_sha()}"
    )
    out_dir.mkdir(parents=True)
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    days = [dt.date.today() + dt.timedelta(days=2 + i) for i in range(a.days)]
    rows: list[dict] = []
    try:
        limits = httpx.Limits(
            max_connections=a.workers * 2 + 10, max_keepalive_connections=a.workers * 2
        )
        async with httpx.AsyncClient(base_url=API, timeout=60, limits=limits) as c:
            admin = await login(c, *ADMIN)
            users = await make_users(c, a.workers)
            rids = [
                await create_room(c, admin) for _ in range(a.workers)
            ]  # worker i writes only to rids[i]
            for ratio in a.read_ratios:
                for mode in ("off", "on"):
                    out = {
                        "read": [],
                        "write_book": [],
                        "write_cancel": [],
                        "checks": 0,
                        "stale": 0,
                    }
                    t0 = time.perf_counter()
                    await asyncio.gather(
                        *(
                            worker(
                                i,
                                c,
                                users[i],
                                rids[i],
                                rids,
                                days,
                                ratio,
                                mode,
                                t0 + a.warmup + a.duration,
                                t0 + a.warmup,
                                a.seed,
                                out,
                            )
                            for i in range(a.workers)
                        )
                    )
                    row = summarize(a, ratio, mode, out)
                    rows.append(row)
                    print(
                        f"ratio={ratio:<5} cache={mode:<3} reads/s={row['reads_per_s']:>7} p50={row['p50_ms']:>6}ms "
                        f"p95={row['p95_ms']:>6}ms p99={row['p99_ms']:>6}ms hit={row['hit_rate']:.2f} "
                        f"err={row['read_errors']} stale={row['stale']}/{row['stale_checks']}",
                        flush=True,
                    )
    finally:
        await pool.execute(CLEANUP_SQL)
        await pool.close()
    with open(out_dir / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    bad = any(r["stale"] or r["read_errors"] for r in rows)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "ok": not bad,
                "args": vars(a),
                "note": a.note,
                "git_sha": git_sha(),
                "api": API,
                "platform": platform.platform(),
                "python": sys.version.split()[0],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"\n{'OK' if not bad else 'PROBLEMS: stale reads or errors'}: results in {out_dir}"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--warmup", type=float, default=3.0)
    ap.add_argument(
        "--days", type=int, default=3, help="distinct dates in the read distribution"
    )
    ap.add_argument("--read-ratios", type=float, nargs="+", default=[0.95, 0.8, 0.5])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--note", default="")
    sys.exit(asyncio.run(main(ap.parse_args())))
