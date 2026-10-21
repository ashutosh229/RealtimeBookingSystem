# ADR-0004: Database concurrency strategy
Status: Accepted | Date: 2026-10-21

## Context
Open decision from the baseline document (D4); resolved in HLD section 3.

## Decision
Per-slot usage ledger with atomic conditional upserts; exclusion constraint on individual resources as defense in depth.

## Consequences
Rationale: One mechanism for all three resource classes, enforced by the database.
Cost accepted: Extra writes per slot; hot rows under heavy contention.
