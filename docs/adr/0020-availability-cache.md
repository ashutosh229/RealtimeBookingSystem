# ADR-0020: Version-stamped availability cache (Phase 4)
Status: Accepted | Date: 2026-11-11

## Decision
Day views of availability are cached in Redis under keys that include a per-resource version counter, read before the database query so a fill that races an invalidation lands under a dead version. Invalidation has two layers: a bump right after each committing change (read-your-writes) and a cache consumer that bumps again from the outbox events (covers a lost bump); a 10 s TTL with jitter is the last backstop. Single-flight limits concurrent loads. Redis errors fail open to PostgreSQL. Range queries and Cache-Control: no-cache bypass. Booking never reads the cache.

## Consequences
Rationale: cached availability is advisory; correctness stays in PostgreSQL (I3).
Cost accepted: the JWT user lookup still hits the database on every request, which limits the gain; a view can be stale for up to the TTL if both invalidation layers fail; counters are per process.
