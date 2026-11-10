# ADR-0018: Surge protection by admission control and simulated credits (C3)
Status: Accepted | Date: 2026-11-10

## Decision
Admission control sits in front of the allocation policy: a per-user token bucket, tail drop on queue length, exponential backoff with jitter for rejected requests, and a simulated credit wallet whose price rises with the backlog (held in escrow, spent on a win, refunded on expiry). Evaluated in the simulator under a flash-crowd trace. The live port of the token bucket waits for Redis (Phase 4); credits stay simulation-only (A8).

## Consequences
Rationale: Sub-theme 6 asks for credit-based and network-inspired surge management compared on satisfaction, rejection and surge handling.
Cost accepted: admission control cannot create seats and can lower utilization when too strict; a request keeps its original arrival time for waiting and patience, so a retried request has less patience left.
