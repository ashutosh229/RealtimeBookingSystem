"""E5: failure injection. Run ON the VM, with 3 API replicas deployed:

    sudo -v                                  # caches the sudo password; RabbitMQ and Postgres faults need it
    API_REPLICAS=3 ./deploy/native/deploy.sh main
    ./.venv/bin/pip install httpx
    ./deploy/native/run.sh python ../bench/chaos.py                          # every scenario
    ./deploy/native/run.sh python ../bench/chaos.py --scenarios none api_kill

A client keeps booking and cancelling with retries (same Idempotency-Key per attempt, like the mobile app).
After each fault, the database is checked: no lost bookings, no capacity violations, every event published,
exactly one notification per booking event.
"""

import argparse
import asyncio
import csv
import datetime as dt
import os
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
SC = ["supervisorctl", "-c", str(ROOT / "run" / "supervisord.conf")]
BASE = os.environ.get("CHAOS_BASE", "http://127.0.0.1:3000")
DSN = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
ADMIN = ("admin@campus.test", os.environ.get("SEED_PASSWORD", "password123"))
PW = "chaos-password-1"
RABBIT = ["sudo", "-n", "-H", "-u", "rabbitmq"]

RS = "(SELECT resource_id FROM resources WHERE name LIKE 'chaos-%')"
BK = f"(SELECT booking_id FROM bookings WHERE resource_id IN {RS})"
US = "(SELECT user_id FROM users WHERE email LIKE '%@chaos.test')"
CLEANUP = f"""
DELETE FROM processed_events WHERE event_id IN (SELECT event_id FROM outbox_events WHERE aggregate_id IN {BK} OR aggregate_id IN {RS});
DELETE FROM outbox_events WHERE aggregate_id IN {BK} OR aggregate_id IN {RS};
DELETE FROM allocation_records WHERE booking_id IN {BK};
DELETE FROM booking_status_history WHERE booking_id IN {BK};
DELETE FROM waitlist_entries WHERE booking_id IN {BK};
DELETE FROM bookings WHERE resource_id IN {RS};
DELETE FROM slot_usage WHERE resource_id IN {RS};
DELETE FROM resources WHERE name LIKE 'chaos-%';
DELETE FROM notifications WHERE user_id IN {US};
DELETE FROM idempotency_keys WHERE user_id IN {US};
DELETE FROM refresh_tokens WHERE user_id IN {US};
DELETE FROM users WHERE email LIKE '%@chaos.test';
"""
INV = (
    "SELECT count(*) FROM slot_usage s WHERE s.resource_id = ANY($1) AND (s.used > s.capacity OR s.used <> "
    "COALESCE((SELECT SUM(b.quantity) FROM bookings b WHERE b.resource_id = s.resource_id"
    " AND b.status IN ('CONFIRMED','COMPLETED') AND b.period @> s.slot_start), 0))"
)


def sh(cmd, check=True) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def kill_program(name: str) -> None:
    os.kill(int(sh(SC + ["pid", name])), 9)  # kill -9: the supervisor restarts it


def rabbit_start() -> None:
    sh(RABBIT + ["rabbitmq-server", "-detached"])
    sh(RABBIT + ["rabbitmqctl", "await_startup"])


SCENARIOS = {  # name -> (inject, heal)   heal=None: the supervisor restarts the process by itself
    "none": (None, None),
    "api_kill": (lambda: kill_program("api:api_2"), None),
    "consumers_kill": (lambda: kill_program("consumers"), None),
    "relay_kill": (lambda: kill_program("relay"), None),
    "rabbit_down": (lambda: sh(RABBIT + ["rabbitmqctl", "stop"]), rabbit_start),
    "redis_down": (
        lambda: sh(["redis-cli", "-h", "127.0.0.1", "shutdown", "nosave"], check=False),
        lambda: sh([str(ROOT / "deploy/native/services.sh"), "start"]),
    ),
    "postgres_crash": (
        lambda: sh(
            ["sudo", "-n", "pg_ctlcluster", "16", "main", "stop", "-m", "immediate"]
        ),
        lambda: sh(["sudo", "-n", "pg_ctlcluster", "16", "main", "start"]),
    ),
}
NEEDS_SUDO = {"rabbit_down", "redis_down", "postgres_crash"}


class Stats:
    def __init__(self):
        self.ok, self.err = defaultdict(int), defaultdict(int)
        self.created, self.cancelled = set(), set()
        self.gave_up_book = self.gave_up_other = self.unexpected = 0
        self.fault_s = self.heal_s = None


async def call(c, st, t0, method, path, retries=6, **kw):
    for _ in range(retries):
        try:
            r = await c.request(method, path, **kw)
            if r.status_code < 500:
                st.ok[int(time.monotonic() - t0)] += 1
                return r
        except httpx.HTTPError:
            pass
        st.err[int(time.monotonic() - t0)] += 1
        await asyncio.sleep(0.5)
    return None


async def worker(c, st, t0, stop_at, headers, rid):
    n = 0
    while time.monotonic() < stop_at:
        n += 1
        day = dt.date.today() + dt.timedelta(days=2 + n % 10)
        start = dt.datetime(day.year, day.month, day.day, 9 + n % 10, tzinfo=dt.UTC)
        body = {
            "resource_id": rid,
            "start_time": start.isoformat(),
            "end_time": (start + dt.timedelta(hours=1)).isoformat(),
            "quantity": 1,
        }
        key = (
            uuid.uuid4().hex
        )  # one key per attempt, reused by the retries inside call()
        r = await call(
            c,
            st,
            t0,
            "POST",
            "/v1/bookings",
            headers={**headers, "Idempotency-Key": key},
            json=body,
        )
        if r is None:
            st.gave_up_book += 1
            continue
        if r.status_code != 201:
            st.unexpected += 1
            continue
        bid = r.json()["booking_id"]
        st.created.add(bid)
        r2 = await call(
            c, st, t0, "POST", f"/v1/bookings/{bid}/cancel", headers=headers
        )
        if r2 is None:
            st.gave_up_other += 1
        elif r2.status_code == 200:
            st.cancelled.add(bid)
        else:
            st.unexpected += 1


async def setup(c, n):
    tag = uuid.uuid4().hex[:6]
    r = await c.post("/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    r.raise_for_status()
    admin = {"Authorization": f"Bearer {r.json()['access_token']}"}
    sem = asyncio.Semaphore(8)

    async def one(i):
        async with sem:
            email = f"{tag}{i}@chaos.test"
            (
                await c.post(
                    "/v1/auth/register",
                    json={"email": email, "name": "c", "password": PW},
                )
            ).raise_for_status()
            t = await c.post("/v1/auth/login", json={"email": email, "password": PW})
            t.raise_for_status()
            h = {"Authorization": f"Bearer {t.json()['access_token']}"}
            uid = (await c.get("/v1/users/me", headers=h)).json()["user_id"]
            room = await c.post(
                "/v1/admin/resources",
                headers=admin,
                json={
                    "name": f"chaos-{tag}-{i}",
                    "type": "ROOM",
                    "capacity": 100,
                    "slot_minutes": 60,
                    "open_time": "00:00",
                    "close_time": "23:59",
                    "timezone": "UTC",
                    "max_slots_per_booking": 4,
                    "max_quantity_per_booking": 1,
                },
            )
            room.raise_for_status()
            return h, uid, room.json()["resource_id"]

    return await asyncio.gather(*(one(i) for i in range(n)))


async def wait_ready(c, timeout=90) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if (await c.get("/readyz")).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    return False


async def db_connect(timeout=90):
    end = time.monotonic() + timeout
    while True:
        try:
            return await asyncpg.connect(DSN, timeout=5)
        except Exception:
            if time.monotonic() > end:
                raise
            await asyncio.sleep(1)


async def verify(st, uids, rids, settle_max) -> dict:
    conn = await db_connect()
    try:
        rid_u, uid_u = [uuid.UUID(r) for r in rids], [uuid.UUID(u) for u in uids]
        t_settle = time.monotonic()
        while True:
            db = {
                r["id"]: r["s"]
                for r in await conn.fetch(
                    "SELECT booking_id::text AS id, status::text AS s FROM bookings WHERE resource_id = ANY($1)",
                    rid_u,
                )
            }
            unpub = await conn.fetchval(
                "SELECT count(*) FROM outbox_events WHERE published_at IS NULL AND (aggregate_id = ANY($1)"
                " OR aggregate_id IN (SELECT booking_id FROM bookings WHERE resource_id = ANY($1)))",
                rid_u,
            )
            notif = {
                r["type"]: r["n"]
                for r in await conn.fetch(
                    "SELECT type, count(*) AS n FROM notifications WHERE user_id = ANY($1) GROUP BY type",
                    uid_u,
                )
            }
            exp_conf, exp_canc = len(db), sum(
                1 for s in db.values() if s == "CANCELLED"
            )
            conf_diff = (
                notif.get("BookingConfirmed", 0) - exp_conf
            )  # < 0 lost, > 0 duplicated
            canc_diff = notif.get("BookingCancelled", 0) - exp_canc
            if (
                unpub == 0 and conf_diff == 0 and canc_diff == 0
            ) or time.monotonic() - t_settle > settle_max:
                break
            await asyncio.sleep(3)
        inv = await conn.fetchval(INV, rid_u)
        lost = len(st.created - set(db))
        unseen = len(set(db) - st.created)
        ok = (
            lost == 0
            and inv == 0
            and unpub == 0
            and conf_diff == 0
            and canc_diff == 0
            and unseen <= st.gave_up_book
            and st.unexpected == 0
        )
        return {
            "bookings_in_db": len(db),
            "lost_bookings": lost,
            "unseen_in_db": unseen,
            "invariant_violations": inv,
            "unpublished_events": unpub,
            "confirmed_notif_diff": conf_diff,
            "cancelled_notif_diff": canc_diff,
            "settle_s": round(time.monotonic() - t_settle, 1),
            "passed": ok,
        }
    finally:
        await conn.close()


async def run_scenario(name, a, c, out_dir) -> dict:
    inject, heal = SCENARIOS[name]
    if name in NEEDS_SUDO and subprocess.run(["sudo", "-n", "true"]).returncode != 0:
        raise SystemExit("sudo needs a password: run `sudo -v` and start again")
    await wait_ready(c)
    people = await setup(c, a.workers)
    st, t0 = Stats(), time.monotonic()
    stop_at = t0 + a.load

    async def chaos():
        if inject is None:
            return
        await asyncio.sleep(a.fault_at)
        st.fault_s = time.monotonic() - t0
        await asyncio.to_thread(inject)
        if heal is not None:
            await asyncio.sleep(a.outage)
            st.heal_s = time.monotonic() - t0
            await asyncio.to_thread(heal)

    await asyncio.gather(
        chaos(), *(worker(c, st, t0, stop_at, h, rid) for h, _u, rid in people)
    )
    ready = await wait_ready(c)
    res = await verify(
        st, [u for _h, u, _r in people], [r for _h, _u, r in people], a.settle
    )
    errs = sorted(s for s, v in st.err.items() if v)
    res.update(
        {
            "scenario": name,
            "ops_ok": sum(st.ok.values()),
            "attempt_errors": sum(st.err.values()),
            "gave_up_book": st.gave_up_book,
            "gave_up_other": st.gave_up_other,
            "unexpected": st.unexpected,
            "first_error_s": errs[0] if errs else "",
            "last_error_s": errs[-1] if errs else "",
            "recovery_s": (
                (errs[-1] - st.fault_s) if (errs and st.fault_s is not None) else 0
            ),
            "ready_after": ready,
        }
    )
    with open(out_dir / f"timeline_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["second", "ok", "errors"])
        for s in range(int(a.load) + 1):
            w.writerow([s, st.ok.get(s, 0), st.err.get(s, 0)])
    return res


async def main(a) -> int:
    sha = sh(["git", "rev-parse", "--short", "HEAD"], check=False) or "nogit"
    out_dir = (
        ROOT / "bench" / "results" / f"chaos-{time.strftime('%Y%m%d-%H%M%S')}_{sha}"
    )
    out_dir.mkdir(parents=True)
    rows = []
    try:
        async with httpx.AsyncClient(
            base_url=BASE, timeout=10, limits=httpx.Limits(max_connections=200)
        ) as c:
            for name in a.scenarios:
                print(f"--- {name}", flush=True)
                row = await run_scenario(name, a, c, out_dir)
                rows.append(row)
                print(
                    f"{'PASS' if row['passed'] else 'FAIL'}  {name:<15} recovery={row['recovery_s']:.0f}s "
                    f"attempt_errors={row['attempt_errors']} gave_up={row['gave_up_book']} lost={row['lost_bookings']} "
                    f"viol={row['invariant_violations']} unpublished={row['unpublished_events']} "
                    f"notif_diff={row['confirmed_notif_diff']}/{row['cancelled_notif_diff']} settle={row['settle_s']}s",
                    flush=True,
                )
                await asyncio.sleep(5)
    finally:
        conn = await db_connect()
        if not a.keep:
            await conn.execute(CLEANUP)
        await conn.close()
    if rows:
        with open(out_dir / "runs.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    ok = all(r["passed"] for r in rows)
    print(f"\n{'ALL PASSED' if ok else 'FAILURES'}: results in {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scenarios", nargs="+", default=list(SCENARIOS), choices=list(SCENARIOS)
    )
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument(
        "--load", type=float, default=40.0, help="seconds of load per scenario"
    )
    ap.add_argument("--fault-at", type=float, default=8.0)
    ap.add_argument(
        "--outage",
        type=float,
        default=15.0,
        help="seconds a stopped service stays down",
    )
    ap.add_argument(
        "--settle",
        type=float,
        default=180.0,
        help="max seconds to wait for events to drain",
    )
    ap.add_argument("--keep", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args())))
