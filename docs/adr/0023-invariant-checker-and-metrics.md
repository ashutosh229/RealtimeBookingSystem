# ADR-0023: Invariant checker and /metrics

Status: Accepted | Date: 2026-11-21

## Decision
A read-only checker recomputes the evidence for I1 and I4 from the tables: slot_usage must equal the units held by CONFIRMED and COMPLETED bookings in every slot (compared in both directions, so a booking without a ledger row is caught) and never exceed capacity; a WAITLISTED booking must have exactly one ACTIVE waitlist entry and the reverse. The worker runs it every INVARIANT_CHECK_SECONDS (60) over the last INVARIANT_LOOKBACK_DAYS (3) and logs a violation at ERROR with examples. python -m app.admin.invariants [--all] runs it once and exits 1 on a violation, so a load test can end with it. GET /metrics returns Prometheus text computed from the database at scrape time (invariant violations, outbox backlog and its age, waitlist length, bookings by status, attempts by outcome and reason); nginx does not proxy it to the public port.

## Consequences
Rationale: the Definition of Done needs zero violations across a mixed load, and gauges taken from the database agree across API replicas, which per-process counters would not.
Cost accepted: the checker scans the window's bookings, so a long window on a large database costs a few seconds per run; latency histograms are not exported (bench/ measures latency); no Prometheus or Grafana runs on the VM, so /metrics is read with curl.
