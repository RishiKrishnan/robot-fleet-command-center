import pytest

from fleet.config import FleetConfig, Robot


@pytest.fixture
def two_robots() -> FleetConfig:
    return FleetConfig(
        robots=[
            Robot(name="arm-01", host="192.168.10.1", type="arm", tags=["production"]),
            Robot(name="mobile-01", host="192.168.10.11", type="mobile", tags=["staging"]),
        ]
    )


@pytest.fixture
def arm_robot() -> Robot:
    return Robot(name="arm-01", host="192.168.10.1", type="arm", tags=["production"])
