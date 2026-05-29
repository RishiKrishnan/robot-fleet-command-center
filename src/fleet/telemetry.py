"""Simulated robot telemetry.

In production this module would poll each robot's telemetry endpoint
(HTTP health API, ROS topic, MQTT broker, etc.) and return structured state.
Here we simulate via a seeded RNG so results are deterministic and testable:
the same robot name produces the same telemetry profile within a 30-second
bucket, giving realistic-looking variance across the fleet.

Inject failure_modes per robot name to force specific failure scenarios in
development, demos, or integration tests.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final

from fleet.config import Robot

SOFTWARE_VERSIONS: Final = ("2.1.0", "2.1.1", "2.2.0")
TASK_NAMES: Final = ("idle", "patrol", "charging", "inspection", "homing", "error")

# Failure modes accepted by TelemetrySampler
FAILURE_MODES: Final = frozenset({"unreachable", "timeout", "degraded"})


@dataclass
class RobotTelemetry:
    robot: str
    host: str
    battery_pct: float
    latency_ms: float
    software_version: str
    last_seen: str  # ISO 8601 UTC
    current_task: str
    health_score: float  # 0.0–1.0 composite
    operational_state: str  # online | degraded | unreachable

    @property
    def is_healthy(self) -> bool:
        return self.operational_state == "online" and self.health_score >= 0.7


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_stale(rng: random.Random) -> str:
    delta = timedelta(seconds=rng.randint(300, 1800))
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _health_score(battery: float, latency: float, task: str) -> float:
    battery_score = battery / 100
    latency_score = max(0.0, 1.0 - latency / 200)
    task_score = 0.3 if task == "error" else 1.0
    return round(0.4 * battery_score + 0.4 * latency_score + 0.2 * task_score, 2)


class TelemetrySampler:
    """Generates simulated telemetry for a fleet of robots.

    Args:
        failure_modes: Maps robot names (or hosts) to a failure mode string.
            Accepted values: "unreachable", "timeout", "degraded".
        seed: Fix the RNG seed for deterministic output. Useful in tests.
            When None, a 30-second time bucket seeded by robot name is used.
    """

    def __init__(
        self,
        failure_modes: dict[str, str] | None = None,
        seed: int | None = None,
    ) -> None:
        self.failure_modes: dict[str, str] = failure_modes or {}
        self._seed = seed

    def sample(self, robot: Robot) -> RobotTelemetry:
        """Return current simulated telemetry for a single robot."""
        if self._seed is not None:
            rng = random.Random(self._seed ^ hash(robot.name))
        else:
            rng = random.Random(hash(robot.name) ^ (int(time.time()) // 30))

        mode = self.failure_modes.get(robot.name) or self.failure_modes.get(robot.host)

        if mode == "unreachable":
            return self._unreachable(robot)
        if mode == "timeout":
            return self._timeout(robot, rng)
        if mode == "degraded":
            return self._degraded(robot, rng)
        return self._online(robot, rng)

    def sample_fleet(self, robots: list[Robot]) -> list[RobotTelemetry]:
        """Sample telemetry for every robot in the fleet."""
        return [self.sample(r) for r in robots]

    # --- private helpers ------------------------------------------------

    @staticmethod
    def _unreachable(robot: Robot) -> RobotTelemetry:
        return RobotTelemetry(
            robot=robot.name,
            host=robot.host,
            battery_pct=0.0,
            latency_ms=0.0,
            software_version="unknown",
            last_seen=_iso_now(),
            current_task="unknown",
            health_score=0.0,
            operational_state="unreachable",
        )

    @staticmethod
    def _timeout(robot: Robot, rng: random.Random) -> RobotTelemetry:
        return RobotTelemetry(
            robot=robot.name,
            host=robot.host,
            battery_pct=round(rng.uniform(10, 60), 1),
            latency_ms=round(rng.uniform(5000, 30000), 1),
            software_version=rng.choice(SOFTWARE_VERSIONS),
            last_seen=_iso_stale(rng),
            current_task="unknown",
            health_score=round(rng.uniform(0.1, 0.35), 2),
            operational_state="degraded",
        )

    @staticmethod
    def _degraded(robot: Robot, rng: random.Random) -> RobotTelemetry:
        battery = round(rng.uniform(5, 25), 1)
        latency = round(rng.uniform(200, 800), 1)
        task = rng.choice(("error", "patrol", "idle"))
        return RobotTelemetry(
            robot=robot.name,
            host=robot.host,
            battery_pct=battery,
            latency_ms=latency,
            software_version=rng.choice(SOFTWARE_VERSIONS),
            last_seen=_iso_now(),
            current_task=task,
            health_score=_health_score(battery, latency, task),
            operational_state="degraded",
        )

    @staticmethod
    def _online(robot: Robot, rng: random.Random) -> RobotTelemetry:
        battery = round(rng.uniform(40, 100), 1)
        latency = round(rng.uniform(2, 80), 1)
        task = rng.choice(TASK_NAMES)
        score = _health_score(battery, latency, task)
        state = "online" if score >= 0.6 else "degraded"
        return RobotTelemetry(
            robot=robot.name,
            host=robot.host,
            battery_pct=battery,
            latency_ms=latency,
            software_version=rng.choice(SOFTWARE_VERSIONS),
            last_seen=_iso_now(),
            current_task=task,
            health_score=score,
            operational_state=state,
        )
