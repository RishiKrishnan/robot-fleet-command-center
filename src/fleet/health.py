from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def check_fleet_health(
    config: FleetConfig,
    executor: Executor,
    *,
    max_workers: int | None = None,
) -> list[RobotHealth]:
    """Run health checks across every robot in the fleet concurrently.

    Results are returned in config order. A worker that raises unexpectedly
    (beyond what check_robot_health already guards) is captured as UNKNOWN.
    """
    robots = config.robots
    if not robots:
        return []

    workers = max_workers or min(len(robots), 32)
    ordered: dict[int, RobotHealth] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(check_robot_health, robot, executor): i
            for i, robot in enumerate(robots)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            robot = robots[idx]
            try:
                health = future.result()
            except Exception:
                logger.exception("Health worker raised unexpectedly for %s", robot.name)
                health = RobotHealth(
                    robot=robot.name,
                    host=robot.host,
                    status=HealthStatus.UNKNOWN,
                    message="worker raised unexpectedly",
                    duration_ms=0.0,
                )
            log_level = logging.INFO if health.status == HealthStatus.HEALTHY else logging.WARNING
            logger.log(log_level, "[%s] %s — %s", robot.name, health.status.value, health.message)
            ordered[idx] = health

    return [ordered[i] for i in range(len(robots))]
