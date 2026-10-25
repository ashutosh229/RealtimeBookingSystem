import pytest

from app.platform.errors import ApiError
from app.resources.policy import policy_for

ROOM = {"max_quantity_per_booking": 4, "eligible_groups": []}


def test_exclusivity_flags():
    assert policy_for("SEAT").is_exclusive
    assert not policy_for("ROOM").is_exclusive
    assert not policy_for("COMPUTE_POOL").is_exclusive


def test_seat_quantity_must_be_one():
    assert policy_for("SEAT").required_quantity({"max_quantity_per_booking": 1}, 1) == 1
    with pytest.raises(ApiError) as ei:
        policy_for("SEAT").required_quantity({"max_quantity_per_booking": 1}, 2)
    assert ei.value.code == "QUANTITY_OUT_OF_RANGE"


@pytest.mark.parametrize("q,ok", [(0, False), (1, True), (4, True), (5, False)])
def test_room_quantity_bounds(q, ok):
    if ok:
        assert policy_for("ROOM").required_quantity(ROOM, q) == q
    else:
        with pytest.raises(ApiError):
            policy_for("ROOM").required_quantity(ROOM, q)


def test_eligibility():
    p = policy_for("COMPUTE_POOL")
    p.check_eligibility({"eligible_groups": []}, {"user_group": "ug"})  # open to all
    p.check_eligibility({"eligible_groups": ["pg"]}, {"user_group": "pg"})
    with pytest.raises(ApiError) as ei:
        p.check_eligibility({"eligible_groups": ["pg"]}, {"user_group": "ug"})
    assert ei.value.status == 403 and ei.value.code == "NOT_ELIGIBLE"
