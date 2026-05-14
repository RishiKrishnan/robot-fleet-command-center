from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from fleet.config import FleetConfig, Robot
from fleet.executor import Executor

logger = logging.getLogger(__name__)

_HEALTH_COMMAND = "echo ok"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class RobotHealth:
    robot: str
    host: str
    status: HealthStatus
    message: str
    duration_ms: float


def check_robot_health(robot: Robot, executor: Executor) -> RobotHealth:
    """Run a connectivity health check on a single robot."""
    try:
        result = executor.run(robot, _HEALTH_COMMAND)
    except Exception as exc:
        logger.exception("Unexpected error checking health of %s", robot.name)
        return RobotHealth(
            robot=robot.name,
            host=robot.host,
            status=HealthStatus.UNKNOWN,
            message=str(exc),
            duration_ms=0.0,
        )

    if result.success:
        return RobotHealth(
            robot=robot.name,
            host=robot.host,
            status=HealthStatus.HEALTHY,
            message=f"Responded in {result.duration_ms:.0f}ms",
            duration_ms=result.duration_ms,
        )

    return RobotHealth(
        robot=robot.name,
        host=robot.host,
        status=HealthStatus.UNHEALTHY,
        message=result.stderr or "Non-zero exit code",
        duration_ms=result.duration_ms,
    )


def check_fleet_health(config: FleetConfig, executor: Executor) -> list[RobotHealth]:
    """Run health checks across every robot in the fleet."""
    results = []
    for robot in config.robots:
        health = check_robot_health(robot, executor)
        log_level = logging.INFO if health.status == HealthStatus.HEALTHY else logging.WARNING
        logger.log(log_level, "[%s] %s — %s", robot.name, health.status.value, health.message)
        results.append(health)
    return results
