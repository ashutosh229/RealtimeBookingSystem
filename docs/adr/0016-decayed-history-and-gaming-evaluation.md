# ADR-0016: Decayed history (FAIR_SHARE_D) and gaming evaluation (B3, B4)
Status: Accepted | Date: 2026-11-07

## Decision
FAIR_SHARE_D ranks by exponentially decayed usage, sum of 0.5^(age_days/half_life) over wins in the window (default half-life 7 days, window 28 days), then longer wait, then queue order. Gaming is evaluated in the simulator: cancel-hoarding (a late-cancelled win either counts toward usage, the live rule for cancels within one hour of start, or not) and duplicate accounts (an owner's requests split over k accounts).

## Consequences
Rationale: a hard window forgets abruptly; decay removes the cliff. Sybil resistance is an identity problem (one verified account per person) that no ranking rule can solve; the experiment quantifies the exposure.
Cost accepted: the live policy needs a wider window than the default 14 days to show its benefit; early cancellations are treated as real releases and are not modelled as abuse.
