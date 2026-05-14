from __future__ import annotations

import logging
import time
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
