# ADR-0010: Performance targets
Status: Accepted | Date: 2026-10-21

## Context
Open decision from the baseline document (D10); resolved in HLD section 3.

## Decision
p95 under 300 ms for reads and 500 ms for booking, at 200 virtual users on a 2-vCPU API and 2-vCPU database; confirm after the first benchmark.

## Consequences
Rationale: Realistic for a prototype.
Cost accepted: Targets may be revised with evidence.
