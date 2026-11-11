from uuid import UUID

from app.messaging.events import _Envelope

MESSAGES = {
    "BookingConfirmed": "Your booking is confirmed.",
    "BookingWaitlisted": "You are on the waitlist.",
    "BookingPromoted": "A seat opened up: your waitlisted booking is now confirmed.",
    "BookingCancelled": "Your booking was cancelled.",
    "BookingExpired": "Your waitlist request expired.",
}


def notification_for(event: _Envelope) -> tuple[UUID, str, dict] | None:
    """(user_id, type, payload) for the in-app inbox, or None when the event concerns nobody."""
    message = MESSAGES.get(event.event_type)
    if message is None:
        return None
    p = event.payload
    return (
        p.user_id,
        event.event_type,
        {**p.model_dump(mode="json"), "message": message},
    )
