# ADR-0022: Live per-user rate limit (C3)

Status: Accepted | Date: 2026-11-21

## Decision
The token bucket of ADR-0018 now also runs in the live API. Each booking request (POST /bookings and /waitlists) takes one token from a per-user bucket held in Redis and updated by one Lua script, so all API replicas share the state and use Redis time. An empty bucket returns 429 RATE_LIMITED with Retry-After before any database work, and the refusal is recorded in booking_attempts like any other rejection. It is off by default (RATE_LIMIT_ENABLED=false); RATE_LIMIT_PER_SECOND (1.0) and RATE_LIMIT_BURST (10) set the refill and the burst. Redis errors fail open, so correctness never depends on it (I3). Credits remain simulation-only (A8).

## Consequences
Rationale: gives sub-theme 6 a real network-inspired surge control to measure against the unprotected system, and keeps a flooding user from costing a transaction per request.
Cost accepted: every refused request still writes one attempts row, which is the evidence sub-theme 6 needs but is write load under a flood; an idempotent replay also spends a token; the limit is per user, so many accounts can still add up; a too-strict limit lowers utilization, as ADR-0018 already noted.
