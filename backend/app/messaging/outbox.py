from app.messaging.events import _Envelope


async def add(conn, event: _Envelope) -> None:
    """Write an event to the outbox. Must be called inside the transaction that changes state (I6)."""
    await conn.execute(
        "INSERT INTO outbox_events (event_id, aggregate_type, aggregate_id, event_type, schema_version, payload)"
        " VALUES ($1, $2, $3, $4, $5, $6)",
        event.event_id,
        event.aggregate_type,
        event.aggregate_id,
        event.event_type,
        event.schema_version,
        event.payload.model_dump(mode="json"),
    )
