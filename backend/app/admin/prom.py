"""Prometheus text exposition for GET /metrics (HLD section 13, adapted).

Every number is computed from PostgreSQL at scrape time, so all API replicas report the same
values (per-process counters would differ between replicas behind the load balancer). The
endpoint is internal: nginx only proxies /v1, /healthz and /readyz, so the public port never
reaches it. Request-latency histograms are not exported; the bench/ scripts measure latency.
"""

import time

import asyncpg

from app.admin import invariants

_TTL = 30.0  # the invariant query scans bookings; do not repeat it on every scrape
_memo: tuple[float, dict] | None = None


def _esc(v: object) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _line(name: str, value: float | int, **labels: object) -> str:
    lab = ",".join(f'{k}="{_esc(v)}"' for k, v in labels.items())
    return f"{name}{{{lab}}} {value}" if lab else f"{name} {value}"


async def _invariants(conn: asyncpg.Connection) -> dict:
    global _memo
    now = time.monotonic()
    if _memo is None or now - _memo[0] > _TTL:
        _memo = (now, await invariants.check(conn, since=invariants.lookback_start(), limit=1))
    return _memo[1]


async def render(conn: asyncpg.Connection) -> str:
    inv = await _invariants(conn)
    out: list[str] = []

    def metric(name: str, help_: str, rows: list[str], kind: str = "gauge") -> None:
        out.extend([f"# HELP {name} {help_}", f"# TYPE {name} {kind}", *rows])

    metric(
        "rtbs_invariant_violations",
        "Rows that break an invariant in the checked window; must stay 0.",
        [
            _line("rtbs_invariant_violations", inv["ledger_violations"], kind="ledger"),
            _line("rtbs_invariant_violations", inv["waitlist_violations"], kind="waitlist"),
        ],
    )
    pending = await conn.fetchrow(
        "SELECT count(*) AS n,"
        " COALESCE(EXTRACT(EPOCH FROM now() - min(created_at)), 0)::float8 AS age"
        " FROM outbox_events WHERE published_at IS NULL"
    )
    metric(
        "rtbs_outbox_pending",
        "Committed events not yet published.",
        [f"rtbs_outbox_pending {pending['n']}"],
    )
    metric(
        "rtbs_outbox_oldest_pending_seconds",
        "Age of the oldest unpublished event.",
        [f"rtbs_outbox_oldest_pending_seconds {pending['age']:.1f}"],
    )
    waiting = await conn.fetchval("SELECT count(*) FROM waitlist_entries WHERE status = 'ACTIVE'")
    metric(
        "rtbs_waitlist_active",
        "Waitlist entries currently waiting.",
        [f"rtbs_waitlist_active {waiting}"],
    )
    metric(
        "rtbs_bookings",
        "Bookings by status.",
        [
            _line("rtbs_bookings", r["n"], status=r["status"])
            for r in await conn.fetch(
                "SELECT status::text AS status, count(*) AS n FROM bookings GROUP BY 1 ORDER BY 1"
            )
        ],
    )
    metric(
        "rtbs_booking_attempts",
        "Retained booking attempts by outcome and rejection reason.",
        [
            _line("rtbs_booking_attempts", r["n"], outcome=r["outcome"], reason=r["reason"] or "")
            for r in await conn.fetch(
                "SELECT outcome, reason, count(*) AS n FROM booking_attempts GROUP BY 1, 2 ORDER BY 1, 2"
            )
        ],
    )
    return "\n".join(out) + "\n"
