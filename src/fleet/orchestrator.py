"""Fleet orchestration — coordinates multi-robot operations.

This module is the controller layer: it knows the semantics of fleet operations
(deploy a version, restart services, fetch logs) but delegates all execution
mechanics to executor.run_fleet_concurrent and all state sampling to
TelemetrySampler. It owns timing and logging context.

In a production system this would be a long-running service. Here it is a
collection of functions called directly by the CLI — simple, testable, and
easy to reason about in an interview setting.
"""

from __future__ import annotations

import logging
import time

from fleet.config import FleetConfig, Robot
from fleet.executor import CommandResult, Executor, run_fleet_concurrent
from fleet.health import RobotHealth, check_fleet_health
from fleet.telemetry import RobotTelemetry, TelemetrySampler

logger = logging.getLogger(__name__)


def deploy(
    robots: list[Robot],
    version: str,
    executor: Executor,
) -> tuple[list[CommandResult], float]:
    """Deploy a software version to a list of robots concurrently.

    Returns (results, wall_time_ms). Per-robot failures are captured in
    results rather than raised, so a failed deployment on one robot does
    not abort the rest of the fleet.
    """
    logger.info("Deploying version %s to %d robot(s)", version, len(robots))
    start = time.monotonic()
    results = run_fleet_concurrent(robots, f"deploy --version {version}", executor)
    duration_ms = (time.monotonic() - start) * 1000
    failed = sum(1 for r in results if not r.success)
    logger.info(
        "Deploy %s complete: %d/%d succeeded in %.0fms",
        version,
        len(results) - failed,
        len(robots),
        duration_ms,
    )
    return results, duration_ms


def restart(
    robots: list[Robot],
    executor: Executor,
) -> tuple[list[CommandResult], float]:
    """Restart the robot-agent service on a list of robots concurrently."""
    logger.info("Restarting robot-agent on %d robot(s)", len(robots))
    start = time.monotonic()
    results = run_fleet_concurrent(robots, "systemctl restart robot-agent", executor)
    duration_ms = (time.monotonic() - start) * 1000
    failed = sum(1 for r in results if not r.success)
    logger.info(
        "Restart complete: %d/%d succeeded in %.0fms",
        len(results) - failed,
        len(robots),
        duration_ms,
    )
    return results, duration_ms


def fetch_logs(
    robot: Robot,
    executor: Executor,
    lines: int = 50,
) -> CommandResult:
    """Fetch recent logs from a single robot via journalctl."""
    logger.debug("Fetching %d log lines from %s", lines, robot.name)
    return executor.run(robot, f"journalctl -u robot-agent -n {lines} --no-pager")


def fleet_status(
    config: FleetConfig,
    executor: Executor,
    sampler: TelemetrySampler,
) -> tuple[list[RobotHealth], list[RobotTelemetry], float]:
    """Collect connectivity health and telemetry for every robot in the fleet.

    Returns (health_results, telemetry_list, wall_time_ms).
    Health checks and telemetry sampling run independently; both cover the
    full fleet regardless of individual failures.
    """
    start = time.monotonic()
    health_results = check_fleet_health(config, executor)
    telemetry = sampler.sample_fleet(config.robots)
    duration_ms = (time.monotonic() - start) * 1000
    return health_results, telemetry, duration_ms
