# ADR-0017: Booking attempts log (C1)
Status: Accepted | Date: 2026-11-09

## Decision
Every booking attempt that reaches the service is recorded in booking_attempts with its outcome (CONFIRMED, WAITLISTED, REJECTED), a reason code, a detail, the HTTP status, and the user's group. Outcomes that commit are written inside the booking transaction; rejections that raise an error are written right after the rollback by a separate insert whose failure never masks the original error. Idempotent replays, key misuse, and schema-invalid requests are not attempts. The live Jain index is computed over everyone who attempted.

## Consequences
Rationale: Sub-theme 6 needs to know who is rejected, when, and why; the previous metric could not see users who were always rejected.
Cost accepted: one extra insert per attempt; the table needs retention (not implemented in v1).
