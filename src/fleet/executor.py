from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol

from fleet.config import Robot

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    robot: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class Executor(Protocol):
    """Interface for executing commands on a remote robot."""

    def run(self, robot: Robot, command: str) -> CommandResult: ...


class MockSSHExecutor:
    """Simulates SSH command execution for testing and local development.

    Swap this for a Paramiko-backed implementation to target real hardware
    without changing any call sites — both satisfy the Executor protocol.
    """

    def __init__(
        self,
        fail_hosts: set[str] | None = None,
        latency_ms: float = 50.0,
    ) -> None:
        # fail_hosts accepts robot names or IP addresses
        self.fail_hosts: set[str] = fail_hosts or set()
        self.latency_ms = latency_ms

    def run(self, robot: Robot, command: str) -> CommandResult:
        logger.debug("Executing on %s (%s): %s", robot.name, robot.host, command)
        start = time.monotonic()
        time.sleep(self.latency_ms / 1000)
        elapsed_ms = (time.monotonic() - start) * 1000

        if robot.host in self.fail_hosts or robot.name in self.fail_hosts:
            logger.warning("Command failed on %s: %s", robot.name, command)
            return CommandResult(
                robot=robot.name,
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"ssh: connect to host {robot.host} port {robot.port}: Connection refused",
                duration_ms=elapsed_ms,
            )

        logger.debug("Command succeeded on %s in %.1fms", robot.name, elapsed_ms)
        return CommandResult(
            robot=robot.name,
            command=command,
            exit_code=0,
            stdout=f"[mock] {command}",
            stderr="",
            duration_ms=elapsed_ms,
        )


def run_fleet_concurrent(
    robots: list[Robot],
    command: str,
    executor: Executor,
    *,
    max_workers: int | None = None,
) -> list[CommandResult]:
    """Fan out a command to all robots concurrently.

    Results are returned in the same order as `robots`. A per-robot executor
    exception is captured as a failed CommandResult rather than propagated, so
    one unresponsive robot never aborts the rest of the fleet.
    """
    if not robots:
        return []

    workers = max_workers or min(len(robots), 32)
    logger.info(
        "Dispatching %r to %d robot(s) with %d worker(s)",
        command, len(robots), workers,
    )

    ordered: dict[int, CommandResult] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(executor.run, robot, command): i
            for i, robot in enumerate(robots)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            robot = robots[idx]
            try:
                result = future.result()
            except Exception as exc:
                logger.error("[%s] executor raised unexpectedly: %s", robot.name, exc)
                result = CommandResult(
                    robot=robot.name,
                    command=command,
                    exit_code=1,
                    stdout="",
                    stderr=str(exc),
                    duration_ms=0.0,
                )
            level = logging.DEBUG if result.success else logging.WARNING
            logger.log(
                level, "[%s] exit=%d in %.0fms",
                robot.name, result.exit_code, result.duration_ms,
            )
            ordered[idx] = result

    return [ordered[i] for i in range(len(robots))]
