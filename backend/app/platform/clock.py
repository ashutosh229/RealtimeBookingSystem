from datetime import UTC, datetime


def now() -> datetime:
    """Single source of 'now' so tests can freeze time. Always call as clock.now()."""
    return datetime.now(UTC)
