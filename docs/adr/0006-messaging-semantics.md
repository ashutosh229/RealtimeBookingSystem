# ADR-0006: Messaging semantics
Status: Accepted | Date: 2026-10-21

## Context
Open decision from the baseline document (D6); resolved in HLD section 3.

## Decision
Transactional outbox, RabbitMQ, 5 retries with backoff, dead-letter queue, consumer dedupe table.

## Consequences
Rationale: Reliable at-least-once delivery without exactly-once machinery.
Cost accepted: Duplicate deliveries must be tolerated by consumers.
