# ADR-0014: Queue-participation weighting (FAIR_SHARE_Q)
Status: Accepted | Date: 2026-10-30

## Context
Sub-theme 4 asks for lower priority for users who repeatedly benefit from high-demand queues, not only for users with many allocations.

## Decision
A win is "contended" when at least K (default 2) other requests were still waiting right after it. Usage = recent allocations + (weight - 1) x recent contended wins; rank by (usage, longest wait, queue order). Contended wins are read from allocation_records (PROMOTE with waiting_after >= K) in the live system, and counted identically in the simulator. weight = 1 is plain fair-share.

## Consequences
Rationale: separates users who win at peak times from users who win off-peak, using data we already audit.
Cost accepted: a contended win cancelled early is still counted, which also blocks book-and-cancel gaming. Under constant load nearly every win is contended and the policy reduces to plain fair-share, so the experiment needs peak/off-peak demand.
