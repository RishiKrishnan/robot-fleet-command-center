"""Fleet reporting — aggregates per-robot results into structured summaries.

FleetReport is the canonical JSON output shape for fleet-level operations:
deploy, restart, status, and report. It mirrors what a real internal dashboard
would consume from a fleet management API.

This module is a pure transformation layer: data in, structured report out.
No I/O, no side effects.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OperationResult:
    """Per-robot result within a FleetReport."""
    robot: str
    success: bool
    exit_code: int
    duration_ms: float
    message: str


@dataclass
class FleetReport:
    """Structured summary of a fleet-wide operation.

    Designed to be serialized directly to JSON for dashboards, alerting
    pipelines, or post-operation audits.
    """
    timestamp: str
    operation: str
    duration_ms: float
    total_robots: int
    succeeded: int
    failed: int
    avg_latency_ms: float
    unhealthy_robots: list[str] = field(default_factory=list)
    results: list[OperationResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_robots == 0:
            return 0.0
        return round(self.succeeded / self.total_robots, 2)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["success_rate"] = self.success_rate
        return d


def build_command_report(
    operation: str,
    results: list,     # list[CommandResult]
    duration_ms: float,
) -> FleetReport:
    """Build a FleetReport from a list of CommandResults (run / deploy / restart)."""
    succeeded = sum(1 for r in results if r.success)
    avg_latency = sum(r.duration_ms for r in results) / len(results) if results else 0.0

    return FleetReport(
        timestamp=_iso_now(),
        operation=operation,
        duration_ms=round(duration_ms, 1),
        total_robots=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        avg_latency_ms=round(avg_latency, 1),
        unhealthy_robots=[r.robot for r in results if not r.success],
        results=[
            OperationResult(
                robot=r.robot,
                success=r.success,
                exit_code=r.exit_code,
                duration_ms=r.duration_ms,
                message=r.stderr if not r.success else r.stdout[:120],
            )
            for r in results
        ],
    )


def build_health_report(
    health_results: list,  # list[RobotHealth]
    duration_ms: float,
) -> FleetReport:
    """Build a FleetReport from a list of RobotHealth results (health / report)."""
    from fleet.health import HealthStatus

    succeeded = sum(1 for h in health_results if h.status == HealthStatus.HEALTHY)
    avg_latency = (
        sum(h.duration_ms for h in health_results) / len(health_results)
        if health_results else 0.0
    )

    return FleetReport(
        timestamp=_iso_now(),
        operation="health",
        duration_ms=round(duration_ms, 1),
        total_robots=len(health_results),
        succeeded=succeeded,
        failed=len(health_results) - succeeded,
        avg_latency_ms=round(avg_latency, 1),
        unhealthy_robots=[h.robot for h in health_results if h.status != HealthStatus.HEALTHY],
        results=[
            OperationResult(
                robot=h.robot,
                success=(h.status == HealthStatus.HEALTHY),
                exit_code=0 if h.status == HealthStatus.HEALTHY else 1,
                duration_ms=h.duration_ms,
                message=h.message,
            )
            for h in health_results
        ],
    )
