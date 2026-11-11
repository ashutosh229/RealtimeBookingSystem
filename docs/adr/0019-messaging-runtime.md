# ADR-0019: Relay, consumers, retry and dead-letter (Phase 4)

Status: Accepted | Date: 2026-11-11

## Decision

A relay process publishes committed outbox rows to a topic exchange with publisher confirms and mandatory routing; delivery is at-least-once. Consumers (notify, promote) process each event in one transaction with a processed_events row, so duplicates are ignored and a failed handler leaves no dedupe row. Failures are forwarded to TTL retry queues (5 s, 30 s, 120 s) that dead-letter back to the consumer's own queue, and to a .dlq queue after 5 deliveries; unparseable messages go straight to the DLQ. Notifications go to an in-app inbox polled by the app. The periodic sweep remains as the safety net for promotion. Relay and consumers run under a compose profile so integration tests are not disturbed.

## Consequences

Rationale: the booking path never depends on the broker (events wait in the outbox), and correctness never depends on exactly-once delivery.
Cost accepted: notification latency of up to the relay poll interval; the relay holds row locks on outbox rows while waiting for the broker's confirm; the DLQ has no replay tool in v1.
