"""Capacity ledger (LLD section 20). All capacity changes in the system go through here.

Call inside the booking transaction. Each function also opens its own nested
transaction (a savepoint when one is already open), so a failure never leaves partial changes.
"""

from datetime import datetime
from uuid import UUID

import asyncpg


class InvariantViolation(Exception):
    """Releasing capacity that was never acquired. A bug if it ever happens."""


class _Insufficient(Exception):
    pass


_ACQUIRE = """
INSERT INTO slot_usage (resource_id, slot_start, used, capacity)
SELECT $1::uuid, s, $3::int, $4::int FROM unnest($2::timestamptz[]) AS s ORDER BY s
ON CONFLICT (resource_id, slot_start) DO UPDATE
   SET used = slot_usage.used + EXCLUDED.used
   WHERE slot_usage.used + EXCLUDED.used <= slot_usage.capacity
RETURNING slot_start
"""


def _check(slots: list[datetime], quantity: int) -> list[datetime]:
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    if not slots:
        raise ValueError("slots must not be empty")
    if len(set(slots)) != len(slots):
        raise ValueError("duplicate slots")
    return sorted(slots)


async def acquire(
    conn: asyncpg.Connection,
    resource_id: UUID,
    slots: list[datetime],
    quantity: int,
    capacity: int,
) -> bool:
    """Add `quantity` to every slot, or change nothing. Returns False if any slot lacks room."""
    ordered = _check(slots, quantity)
    if quantity > capacity:
        return False
    try:
        async with conn.transaction():
            rows = await conn.fetch(_ACQUIRE, resource_id, ordered, quantity, capacity)
            if len(rows) != len(ordered):  # a slot's WHERE failed: it returned no row
                raise _Insufficient
    except _Insufficient:
        return False
    return True


async def release(
    conn: asyncpg.Connection, resource_id: UUID, slots: list[datetime], quantity: int
) -> None:
    """Subtract `quantity` from every slot. Raises InvariantViolation if that would go below zero."""
    ordered = _check(slots, quantity)
    async with conn.transaction():
        # Lock in ascending order first, so releases cannot deadlock with acquires.
        await conn.fetch(
            "SELECT slot_start FROM slot_usage WHERE resource_id = $1 AND slot_start = ANY($2::timestamptz[])"
            " ORDER BY slot_start FOR UPDATE",
            resource_id,
            ordered,
        )
        rows = await conn.fetch(
            "UPDATE slot_usage SET used = used - $3"
            " WHERE resource_id = $1 AND slot_start = ANY($2::timestamptz[]) AND used >= $3"
            " RETURNING slot_start",
            resource_id,
            ordered,
            quantity,
        )
        if len(rows) != len(ordered):
            raise InvariantViolation(
                f"release of {quantity} on {len(ordered)} slots exceeds recorded usage"
            )
