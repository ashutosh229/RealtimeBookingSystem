# ADR-0001: Booking granularity
Status: Accepted | Date: 2026-10-21

## Context
Open decision from the baseline document (D1); resolved in HLD section 3.

## Decision
Fixed slots per resource (30 or 60 min); a booking is a contiguous run of slots.

## Consequences
Rationale: Exact, cheap capacity accounting; no interval sweeps.
Cost accepted: Less flexible than arbitrary intervals.
