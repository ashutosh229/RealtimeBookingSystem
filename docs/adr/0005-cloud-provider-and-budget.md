# ADR-0005: Cloud provider and budget
Status: Accepted | Date: 2026-10-21

## Context
Open decision from the baseline document (D5); resolved in HLD section 3.

## Decision
One low-cost VM running Docker Compose first; managed PostgreSQL only if free or cheap.

## Consequences
Rationale: Cheap and easy to tear down.
Cost accepted: Single host until the scaling test.
