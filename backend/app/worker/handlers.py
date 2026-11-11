import asyncpg

from app.availability import cache as availability_cache
from app.messaging.events import _Envelope
from app.messaging.notify import notification_for
from app.worker import promoter

_AFFECTS_AVAILABILITY = {
    "BookingConfirmed",
    "BookingPromoted",
    "BookingCancelled",
    "CapacityReleased",
    "ResourceUpdated",
}


async def cache_invalidate(conn: asyncpg.Connection, event: _Envelope) -> None:
    """Layer 2 of invalidation. strict: a Redis outage raises, so the message is retried."""
    if event.event_type in _AFFECTS_AVAILABILITY:
        await availability_cache.bump(event.payload.resource_id, strict=True)


async def notify(conn: asyncpg.Connection, event: _Envelope) -> None:
    n = notification_for(event)
    if n is None:
        return
    user_id, type_, payload = n
    await conn.execute(
        "INSERT INTO notifications (user_id, type, payload, event_id) VALUES ($1, $2, $3, $4)"
        " ON CONFLICT (user_id, event_id, type) DO NOTHING",
        user_id,
        type_,
        payload,
        event.event_id,
    )


async def promote(conn: asyncpg.Connection, event: _Envelope) -> None:
    """Event-driven promotion. The periodic sweep remains as the safety net for lost or late events."""
    if event.event_type == "CapacityReleased":
        await promoter.promote_for_resource(conn, event.payload.resource_id)


HANDLERS = {"notify": notify, "promote": promote, "cache": cache_invalidate}
