# ADR-0013: asyncpg directly instead of SQLAlchemy Core
Status: Accepted | Date: 2026-10-22

## Decision
Use asyncpg with hand-written SQL for the booking path. Alembic still manages migrations.

## Consequences
Rationale: ledger upserts, savepoints, and SKIP LOCKED queries are plain SQL, and one less abstraction layer makes transaction boundaries explicit.
Cost accepted: no ORM conveniences; row-to-model mapping is manual.
