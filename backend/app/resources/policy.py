"""Per-type resource rules. The booking engine calls these and never branches on type names."""

from collections.abc import Mapping
from datetime import datetime

from app.platform.errors import ApiError
from app.resources import slots


class ResourcePolicy:
    is_exclusive = (
        False  # True: at most one active booking per slot (also guarded by DB exclusion constraint)
    )

    def validate_interval(
        self, res: Mapping, start: datetime, end: datetime, now: datetime
    ) -> list[datetime]:
        return slots.validate_interval(res, start, end, now)

    def required_quantity(self, res: Mapping, requested: int) -> int:
        if not 1 <= requested <= res["max_quantity_per_booking"]:
            raise ApiError(
                422,
                "QUANTITY_OUT_OF_RANGE",
                f"quantity must be between 1 and {res['max_quantity_per_booking']}",
            )
        return requested

    def check_eligibility(self, res: Mapping, user: Mapping) -> None:
        groups = res["eligible_groups"]
        if groups and user["user_group"] not in groups:
            raise ApiError(403, "NOT_ELIGIBLE", "You are not eligible to book this resource")


class SeatPolicy(ResourcePolicy):
    is_exclusive = True

    def required_quantity(self, res: Mapping, requested: int) -> int:
        if requested != 1:
            raise ApiError(422, "QUANTITY_OUT_OF_RANGE", "a seat is booked with quantity 1")
        return 1


class RoomPolicy(ResourcePolicy):
    pass


class ComputePoolPolicy(ResourcePolicy):
    pass  # duration cap and unit-hour quota arrive with the fair-share work


POLICIES: dict[str, ResourcePolicy] = {
    "SEAT": SeatPolicy(),
    "ROOM": RoomPolicy(),
    "COMPUTE_POOL": ComputePoolPolicy(),
}


def policy_for(resource_type: str) -> ResourcePolicy:
    return POLICIES[resource_type]
