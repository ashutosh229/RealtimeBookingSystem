"""E3: throughput and latency against the number of API replicas. Run from a separate machine.

    ssh -p 2501 -N -L 5433:127.0.0.1:5432 student@10.1.75.53        # other terminal, for the database check
    export BENCH_DB_DSN="postgresql://rtbs:<POSTGRES_PASSWORD from .env.prod>@localhost:5433/rtbs"
    export BENCH_ADMIN_PASSWORD=<SEED_PASSWORD from .env.prod>
    python bench/bench_scaling.py --base http://10.1.75.53:3501 --replicas 2 --note "VM 8 cores, generator on laptop"
Redeploy with API_REPLICAS=N between runs. Workload: 70% availability reads (cached), 30% booking+cancel on a
worker-owned room, so the measurement is throughput, not lock contention.
"""

import argparse
import asyncio
import csv
import datetime as dt
import json
import os
import platform
import random
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import asyncpg
import httpx

sys.path.insert(0, str(Path(__file__).parent))
from bench_cache import (
    ADMIN,
    CLEANUP_SQL,
    create_room,
    git_sha,
    login,
    make_users,
    pct,
)

DSN = os.environ.get("BENCH_DB_DSN", "postgresql://rtbs:change_me@localhost:5432/rtbs")
INV = (
    "SELECT count(*) FROM slot_usage s WHERE s.resource_id = ANY($1) AND (s.used > s.capacity OR s.used <> "
    "COALESCE((SELECT SUM(b.quantity) FROM bookings b WHERE b.resource_id = s.resource_id"
    " AND b.status IN ('CONFIRMED','COMPLETED') AND b.period @> s.slot_start), 0))"
)


async def worker(
    i, c, headers, own, rids, days, t_warm, t_end, read_share, seed, out, tot
) -> None:
    rng, n = random.Random(seed * 1000 + i), 0
    while time.perf_counter() < t_end:
        n += 1
        measured = time.perf_counter() >= t_warm
        if rng.random() < read_share:
            rid, day = rng.choice(rids), rng.choice(days)
            t0 = time.perf_counter()
            try:
                r = await c.get(
                    f"/resources/{rid}/availability",
                    params={"date": day.isoformat()},
                    headers=headers,
                )
                status, inst = r.status_code, r.headers.get("X-Instance", "")
            except httpx.HTTPError:
                status, inst = 0, ""
            if measured:
                out["read"].append(((time.perf_counter() - t0) * 1000, status))
                if inst:
                    out["inst"][inst] += 1
            continue
        day = days[n % len(days)]
        start = dt.datetime(day.year, day.month, day.day, 9 + n % 10, tzinfo=dt.UTC)
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
            status, r = 0, None
        if measured:
            out["book"].append(((time.perf_counter() - t0) * 1000, status))
        if status != 201:
            continue
        tot["created"] += 1
        t0 = time.perf_counter()
        try:
            cr = await c.post(
                f"/bookings/{r.json()['booking_id']}/cancel", headers=headers
            )
            cstatus = cr.status_code
        except httpx.HTTPError:
            cstatus = 0
        if cstatus == 200:
            tot["cancelled"] += 1
        if measured:
            out["cancel"].append(((time.perf_counter() - t0) * 1000, cstatus))


def summarize(a, conc, out) -> dict:
    reads = [ms for ms, st in out["read"] if st == 200]
    books = [ms for ms, st in out["book"] if st == 201]
    n = len(out["read"]) + len(out["book"]) + len(out["cancel"])
    errs = (
        sum(1 for _, s in out["read"] if s != 200)
        + sum(1 for _, s in out["book"] if s != 201)
        + sum(1 for _, s in out["cancel"] if s != 200)
    )
    return {
        "replicas": a.replicas,
        "concurrency": conc,
        "duration_s": a.duration,
        "requests": n,
        "req_per_s": round(n / a.duration, 1),
        "errors": errs,
        "error_rate": round(errs / n, 4) if n else 0.0,
        "read_p50_ms": round(pct(reads, 50), 1),
        "read_p95_ms": round(pct(reads, 95), 1),
        "read_p99_ms": round(pct(reads, 99), 1),
        "book_p50_ms": round(pct(books, 50), 1),
        "book_p95_ms": round(pct(books, 95), 1),
        "book_p99_ms": round(pct(books, 99), 1),
        "instances_seen": len(out["inst"]),
        "instance_share": json.dumps(dict(out["inst"])),
    }


async def main(a) -> int:
    out_dir = (
        Path(__file__).parent
        / "results"
        / f"scaling-r{a.replicas}-{time.strftime('%Y%m%d-%H%M%S')}_{git_sha()}"
    )
    out_dir.mkdir(parents=True)
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    days = [dt.date.today() + dt.timedelta(days=2 + i) for i in range(3)]
    n_max, rows, tot = max(a.concurrency), [], {"created": 0, "cancelled": 0}
    rids: list[str] = []
    try:
        limits = httpx.Limits(
            max_connections=n_max * 2 + 10, max_keepalive_connections=n_max * 2
        )
        async with httpx.AsyncClient(
            base_url=a.base.rstrip("/") + "/v1", timeout=60, limits=limits
        ) as c:
            admin = await login(c, *ADMIN)
            users = await make_users(c, n_max)
            rids = [await create_room(c, admin) for _ in range(n_max)]
            for conc in a.concurrency:
                out = {"read": [], "book": [], "cancel": [], "inst": Counter()}
                t0 = time.perf_counter()
                await asyncio.gather(
                    *(
                        worker(
                            i,
                            c,
                            users[i],
                            rids[i],
                            rids[:conc],
                            days,
                            t0 + a.warmup,
                            t0 + a.warmup + a.duration,
                            a.read_share,
                            a.seed,
                            out,
                            tot,
                        )
                        for i in range(conc)
                    )
                )
                row = summarize(a, conc, out)
                rows.append(row)
                print(
                    f"replicas={a.replicas} conc={conc:<4} req/s={row['req_per_s']:>7} err={row['error_rate']:.4f} "
                    f"read p50/p95/p99={row['read_p50_ms']}/{row['read_p95_ms']}/{row['read_p99_ms']} ms "
                    f"book p50/p95/p99={row['book_p50_ms']}/{row['book_p95_ms']}/{row['book_p99_ms']} ms "
                    f"instances={row['instances_seen']}",
                    flush=True,
                )
        import uuid as _u

        rid_u = [_u.UUID(r) for r in rids]
        confirmed = await pool.fetchval(
            "SELECT count(*) FROM bookings WHERE resource_id = ANY($1) AND status = 'CONFIRMED'",
            rid_u,
        )
        viol = await pool.fetchval(INV, rid_u)
    finally:
        await pool.execute(CLEANUP_SQL)
        await pool.close()
    ok = viol == 0 and confirmed == tot["created"] - tot["cancelled"]
    with open(out_dir / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "ok": ok,
                "invariant_violations": viol,
                "confirmed_in_db": confirmed,
                **tot,
                "args": vars(a),
                "note": a.note,
                "git_sha": git_sha(),
                "platform": platform.platform(),
                "python": sys.version.split()[0],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"\n{'OK' if ok else 'PROBLEM'}: violations={viol}, confirmed in db={confirmed} "
        f"(created {tot['created']} - cancelled {tot['cancelled']}); results in {out_dir}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://10.1.75.53:3501")
    ap.add_argument(
        "--replicas",
        type=int,
        required=True,
        help="label: how many API replicas are deployed",
    )
    ap.add_argument("--concurrency", type=int, nargs="+", default=[32, 64, 128])
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--warmup", type=float, default=5.0)
    ap.add_argument("--read-share", type=float, default=0.7)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--note", default="")
    sys.exit(asyncio.run(main(ap.parse_args())))
