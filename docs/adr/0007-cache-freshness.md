# ADR-0007: Cache freshness
Status: Accepted | Date: 2026-10-21

## Context
Open decision from the baseline document (D7); resolved in HLD section 3.

## Decision
Availability TTL 10 s plus invalidation after commit; resource metadata TTL 5 min. Booking always revalidates in PostgreSQL.

## Consequences
Rationale: Cache stays advisory.
Cost accepted: UI may briefly show stale availability.
