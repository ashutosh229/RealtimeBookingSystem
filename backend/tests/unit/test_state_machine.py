import itertools

import pytest

from app.booking.state_machine import (
    TERMINAL,
    BookingStatus,
    CapacityEffect,
    IllegalTransition,
    can_transition,
    capacity_effect,
    check_transition,
)

S = BookingStatus

# Written out independently of the module's table, so the test can catch mistakes in it.
LEGAL = {
    (S.REQUESTED, S.CONFIRMED),
    (S.REQUESTED, S.WAITLISTED),
    (S.WAITLISTED, S.CONFIRMED),
    (S.WAITLISTED, S.CANCELLED),
    (S.WAITLISTED, S.EXPIRED),
    (S.CONFIRMED, S.CANCELLED),
    (S.CONFIRMED, S.COMPLETED),
    (S.CONFIRMED, S.EXPIRED),
}


@pytest.mark.parametrize("src,dst", list(itertools.product(S, S)))
def test_full_transition_matrix(src, dst):
    if (src, dst) in LEGAL:
        assert can_transition(src, dst)
        check_transition(src, dst)
    else:
        assert not can_transition(src, dst)
        with pytest.raises(IllegalTransition):
            check_transition(src, dst)


def test_terminal_states_have_no_exits():
    assert TERMINAL == {S.CANCELLED, S.COMPLETED, S.EXPIRED}
    for t in TERMINAL:
        for dst in S:
            assert not can_transition(t, dst)


EFFECTS = {
    (S.REQUESTED, S.CONFIRMED): CapacityEffect.ACQUIRE,
    (S.WAITLISTED, S.CONFIRMED): CapacityEffect.ACQUIRE,
    (S.CONFIRMED, S.CANCELLED): CapacityEffect.RELEASE,
    (S.CONFIRMED, S.EXPIRED): CapacityEffect.RELEASE,
    (S.REQUESTED, S.WAITLISTED): CapacityEffect.NONE,
    (S.WAITLISTED, S.CANCELLED): CapacityEffect.NONE,
    (S.WAITLISTED, S.EXPIRED): CapacityEffect.NONE,
    (S.CONFIRMED, S.COMPLETED): CapacityEffect.NONE,
}


@pytest.mark.parametrize("pair,effect", EFFECTS.items())
def test_capacity_effect(pair, effect):
    assert capacity_effect(*pair) == effect


def test_every_legal_transition_has_a_defined_effect():
    assert set(EFFECTS) == LEGAL


def test_capacity_effect_rejects_illegal_pair():
    with pytest.raises(IllegalTransition):
        capacity_effect(S.CANCELLED, S.CONFIRMED)  # cannot re-acquire after cancel
