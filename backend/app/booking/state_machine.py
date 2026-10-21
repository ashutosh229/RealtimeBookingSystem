"""Booking lifecycle rules (LLD section 18). Pure logic, no database access."""

from enum import StrEnum


class BookingStatus(StrEnum):
    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class CapacityEffect(StrEnum):
    ACQUIRE = "ACQUIRE"  # ledger +q on each slot
    RELEASE = "RELEASE"  # ledger -q on each slot
    NONE = "NONE"


class IllegalTransition(Exception):
    def __init__(self, src: BookingStatus, dst: BookingStatus) -> None:
        super().__init__(f"illegal transition {src} -> {dst}")
        self.src, self.dst = src, dst


S = BookingStatus

TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    S.REQUESTED: frozenset({S.CONFIRMED, S.WAITLISTED}),
    S.WAITLISTED: frozenset({S.CONFIRMED, S.CANCELLED, S.EXPIRED}),
    S.CONFIRMED: frozenset({S.CANCELLED, S.COMPLETED, S.EXPIRED}),
    S.CANCELLED: frozenset(),
    S.COMPLETED: frozenset(),
    S.EXPIRED: frozenset(),
}

TERMINAL = frozenset(s for s, targets in TRANSITIONS.items() if not targets)


def can_transition(src: BookingStatus, dst: BookingStatus) -> bool:
    return dst in TRANSITIONS[src]


def check_transition(src: BookingStatus, dst: BookingStatus) -> None:
    if not can_transition(src, dst):
        raise IllegalTransition(src, dst)


def capacity_effect(src: BookingStatus, dst: BookingStatus) -> CapacityEffect:
    """What a legal transition must do to the slot ledger (invariant I4)."""
    check_transition(src, dst)
    if dst == S.CONFIRMED:
        return CapacityEffect.ACQUIRE
    if src == S.CONFIRMED and dst in {S.CANCELLED, S.EXPIRED}:
        return CapacityEffect.RELEASE
    return CapacityEffect.NONE  # includes CONFIRMED -> COMPLETED (past slots stay counted)
