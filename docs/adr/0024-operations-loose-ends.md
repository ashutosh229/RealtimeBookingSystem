# ADR-0024: Attempts retention, dead-letter replay and optional user cache

Status: Accepted | Date: 2026-11-21

## Decision
(1) The sweeper deletes booking_attempts older than ATTEMPTS_RETENTION_DAYS (90; 0 keeps everything) in batches of 5000, using database time. (2) python -m app.messaging.dlq lists, replays (with the attempt counter reset) or purges a dead-letter queue; replay publishes before it acknowledges, and the consumers' dedupe table makes a repeat harmless. (3) The JWT user lookup can be cached per process for USER_CACHE_SECONDS (0, off by default), which saves one query per request.

## Consequences
Rationale: closes the costs accepted in ADR-0017 (no retention), ADR-0019 (no way to replay a dead letter) and ADR-0020 (user lookup on every request).
Cost accepted: with the cache on, a role, group or deactivation change reaches a replica only after the TTL; the connection checkout per request remains, so the gain is one query, not the whole dependency; purged attempts leave the fairness and rejection history, so the retention must exceed any evaluation window.
