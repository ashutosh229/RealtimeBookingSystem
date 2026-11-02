# ADR-0015: Minimum gap between a user's allocations (B2)
Status: Accepted | Date: 2026-11-02

## Decision
A user allocated a slot of a resource type is ineligible for waitlist promotions of that type until the gap has passed (PROMOTION_MIN_GAP_MINUTES, default 0 = off). It is an eligibility filter applied before ranking; skipped candidates are recorded once as SKIP_INELIGIBLE with reason COOLDOWN. The simulator models it as min_gap rounds. The simulator and the promoter both re-rank after every pick.

## Consequences
Rationale: Sub-theme 4 asks for allocation at specified intervals based on previous allocations.
Cost accepted: deployment-wide setting in v1 (per-resource is a natural extension); it can lower utilization when the only waiters are cooling.
