from datetime import time

import pytest

from app.platform.errors import ApiError
from app.resources.service import validate_config

OK = dict(
    type="ROOM",
    capacity=5,
    max_quantity_per_booking=3,
    open_time=time(8),
    close_time=time(22),
    timezone="UTC",
    lat=None,
    lon=None,
)


def test_valid_config_passes():
    validate_config(OK)
    validate_config({**OK, "lat": 12.0, "lon": 77.0})


@pytest.mark.parametrize(
    "override",
    [
        dict(type="SEAT", capacity=2, max_quantity_per_booking=1),
        dict(type="SEAT", capacity=1, max_quantity_per_booking=2),
        dict(max_quantity_per_booking=6),
        dict(open_time=time(22), close_time=time(8)),
        dict(timezone="Not/AZone"),
        dict(lat=12.0),
    ],
)
def test_invalid_configs(override):
    with pytest.raises(ApiError) as ei:
        validate_config({**OK, **override})
    assert ei.value.status == 422
