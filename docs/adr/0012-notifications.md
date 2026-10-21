# ADR-0012: Notifications via in-app inbox and polling
Status: Accepted | Date: 2026-10-21

## Context
Push notifications need Apple credentials on iOS and extra setup on Android, which ADR-0011 rules out. Users still need to learn about confirmations, promotions from the waitlist, and cancellations.

## Decision
- The `q.notify` consumer writes one row per event to the `notifications` table (`user_id`, `type`, `payload`, `event_id`, `created_at`, `read_at`). A unique key on `(user_id, event_id, type)` makes redelivered events harmless.
- The app polls `GET /v1/users/me/notifications?since=<id>` every 10-15 seconds while open, and shows an in-app banner for new items.
- `POST /v1/users/me/notifications/{id}/read` marks items as read.
- Email through a free SMTP sink or free tier stays optional.
- The event pipeline (outbox, RabbitMQ, consumers) is unchanged; only the delivery channel differs.

## Consequences
Rationale: reuses the existing at-least-once pipeline and needs no external accounts.
Cost accepted: users are not notified while the app is closed, and polling adds read load, which the cache and the `(user_id, id DESC)` index absorb. Push can be added later as a second channel on the same consumer.
