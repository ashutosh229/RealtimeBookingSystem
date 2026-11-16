"""Post-deploy smoke test. Usage: python3 deploy/smoke.py https://your-host"""

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/")
failures: list[str] = []


def call(method, path, body=None, token=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, method=method, headers=h, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), r.headers
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), e.headers
        except Exception:  # noqa: BLE001
            return e.code, None, e.headers


def check(ok, label, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not ok:
        failures.append(label)


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


st, _, _ = call("GET", "/healthz")
check(st == 200, "healthz")
st, _, _ = call("GET", "/readyz")
check(st == 200, "readyz (database reachable)")

email = f"smoke-{uuid.uuid4().hex[:10]}@smoke.test"
st, _, _ = call(
    "POST",
    "/v1/auth/register",
    {"email": email, "name": "Smoke", "password": "smoke-password-1"},
)
check(st == 201, "register")
st, tok, _ = call(
    "POST", "/v1/auth/login", {"email": email, "password": "smoke-password-1"}
)
check(st == 200 and tok, "login")
if st != 200:
    sys.exit(1)
T = tok["access_token"]
st, me, _ = call("GET", "/v1/users/me", token=T)
check(st == 200 and me["email"] == email, "me")

st, page, _ = call("GET", "/v1/resources?limit=100", token=T)
seats = [r for r in (page or {}).get("items", []) if r["type"] == "SEAT"]
check(st == 200 and bool(seats), "resources listed (seed loaded)")
if not seats:
    sys.exit(1)
rid = seats[0]["resource_id"]
day = (dt.datetime.now(dt.UTC) + dt.timedelta(days=2)).date().isoformat()
st, a1, h1 = call("GET", f"/v1/resources/{rid}/availability?date={day}", token=T)
check(st == 200 and a1["slots"], "availability")
st, a2, h2 = call("GET", f"/v1/resources/{rid}/availability?date={day}", token=T)
check(
    h2.get("X-Cache") == "HIT",
    "availability cache hit on the second read",
    f"X-Cache={h2.get('X-Cache')}",
)

free = next((s for s in a1["slots"] if s["available"] > 0), None)
check(free is not None, "a free slot exists")
if free is None:
    sys.exit(1)
start = parse(free["start_time"])
body = {
    "resource_id": rid,
    "start_time": start.isoformat(),
    "end_time": (start + dt.timedelta(minutes=a1["slot_minutes"])).isoformat(),
    "quantity": 1,
    "waitlist_if_full": False,
}
key = uuid.uuid4().hex
st, b, _ = call("POST", "/v1/bookings", body, T, {"Idempotency-Key": key})
check(st == 201 and b["status"] == "CONFIRMED", "booking confirmed")
st2, b2, h = call("POST", "/v1/bookings", body, T, {"Idempotency-Key": key})
check(
    st2 == 201
    and b2["booking_id"] == b["booking_id"]
    and h.get("Idempotent-Replay") == "true",
    "same key replays the same booking (no double booking)",
)

delivered = False
for _ in range(15):
    st, n, _ = call("GET", "/v1/users/me/notifications", token=T)
    if st == 200 and any(i["type"] == "BookingConfirmed" for i in n["items"]):
        delivered = True
        break
    time.sleep(1)
check(delivered, "notification delivered (outbox, relay, broker, consumer)")

st, det, _ = call("GET", f"/v1/bookings/{b['booking_id']}", token=T)
check(st == 200 and det["status"] == "CONFIRMED", "booking readable")
st, c, _ = call("POST", f"/v1/bookings/{b['booking_id']}/cancel", token=T)
check(st == 200 and c["status"] == "CANCELLED", "cancelled")
st, a3, h3 = call("GET", f"/v1/resources/{rid}/availability?date={day}", token=T)
slot = next(s for s in a3["slots"] if s["start_time"] == free["start_time"])
check(
    slot["available"] == free["available"] and h3.get("X-Cache") == "MISS",
    "capacity restored and the cache was invalidated",
)

print("\nALL PASSED" if not failures else f"\nFAILED: {', '.join(failures)}")
sys.exit(1 if failures else 0)
