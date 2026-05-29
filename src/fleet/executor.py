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

    Args:
        fail_hosts: Robot names or IPs that always return connection refused.
        latency_ms: Base simulated round-trip latency for healthy robots.
        failure_modes: Per-robot failure scenario overrides. Accepted values:
            "unreachable"    — connection refused (same as fail_hosts)
            "timeout"        — command hangs then fails (2 s simulated)
            "degraded"       — slow response with stderr warnings
            "deploy_failure" — non-zero exit on deploy commands
    """

    def __init__(
        self,
        fail_hosts: set[str] | None = None,
        latency_ms: float = 50.0,
        failure_modes: dict[str, str] | None = None,
    ) -> None:
        self.fail_hosts: set[str] = fail_hosts or set()
        self.latency_ms = latency_ms
        self.failure_modes: dict[str, str] = failure_modes or {}

    def run(self, robot: Robot, command: str) -> CommandResult:
        logger.debug("Executing on %s (%s): %s", robot.name, robot.host, command)
        start = time.monotonic()

        mode = self.failure_modes.get(robot.name) or self.failure_modes.get(robot.host)

        # Explicit fail_hosts always means unreachable
        if robot.host in self.fail_hosts or robot.name in self.fail_hosts:
            mode = "unreachable"

        if mode == "unreachable":
            time.sleep(self.latency_ms / 1000)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning("[%s] unreachable: %s", robot.name, command)
            return CommandResult(
                robot=robot.name,
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"ssh: connect to host {robot.host} port {robot.port}: Connection refused",
                duration_ms=elapsed_ms,
            )

        if mode == "timeout":
            time.sleep(2.0)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning("[%s] timeout executing: %s", robot.name, command)
            return CommandResult(
                robot=robot.name,
                command=command,
                exit_code=1,
                stdout="",
                stderr="ssh: connect to host: Connection timed out",
                duration_ms=elapsed_ms,
            )

        if mode == "degraded":
            time.sleep(max(self.latency_ms, 300) / 1000)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning("[%s] degraded response in %.0fms", robot.name, elapsed_ms)
            return CommandResult(
                robot=robot.name,
                command=command,
                exit_code=0,
                stdout=f"[mock] {command}",
                stderr="WARNING: high memory pressure; process may be unstable",
                duration_ms=elapsed_ms,
            )

        if mode == "deploy_failure" and command.startswith("deploy"):
            time.sleep(self.latency_ms / 1000)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning("[%s] deploy failed: version incompatible", robot.name)
            return CommandResult(
                robot=robot.name,
                command=command,
                exit_code=1,
                stdout="",
                stderr="deploy: target version incompatible with installed firmware",
                duration_ms=elapsed_ms,
            )

        # Healthy path — route to command-aware mock responses
        time.sleep(self.latency_ms / 1000)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.debug("[%s] OK in %.1fms", robot.name, elapsed_ms)
        return self._ok_response(robot, command, elapsed_ms)

    @staticmethod
    def _ok_response(robot: Robot, command: str, elapsed_ms: float) -> CommandResult:
        """Return a realistic mock stdout for known command patterns."""
        if command.startswith("journalctl"):
            stdout = (
                f"May 18 10:00:01 {robot.name} robot-agent[1234]: INFO  dispatcher started\n"
                f"May 18 10:00:02 {robot.name} robot-agent[1234]: INFO  connected to base station\n"
                f"May 18 10:00:15 {robot.name} robot-agent[1234]: INFO  task started: patrol\n"
                f"May 18 10:02:30 {robot.name} robot-agent[1234]: WARN  battery below 30%\n"
                f"May 18 10:05:00 {robot.name} robot-agent[1234]: INFO  task complete, docking"
            )
        elif command.startswith("deploy"):
            stdout = f"deploy: version extracted successfully on {robot.name}"
        elif "systemctl restart" in command:
            stdout = ""
        else:
            stdout = f"[mock] {command}"

        return CommandResult(
            robot=robot.name,
            command=command,
            exit_code=0,
            stdout=stdout,
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
        command,
        len(robots),
        workers,
    )

    ordered: dict[int, CommandResult] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(executor.run, robot, command): i for i, robot in enumerate(robots)
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
                level,
                "[%s] exit=%d in %.0fms",
                robot.name,
                result.exit_code,
                result.duration_ms,
            )
            ordered[idx] = result

    return [ordered[i] for i in range(len(robots))]
