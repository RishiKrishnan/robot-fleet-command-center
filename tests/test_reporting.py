"""Tests for FleetReport and report builder functions."""
import json

from fleet.executor import CommandResult
from fleet.health import HealthStatus, RobotHealth
from fleet.reporting import build_command_report, build_health_report


def _ok(robot: str, duration_ms: float = 10.0) -> CommandResult:
    return CommandResult(robot=robot, command="uptime", exit_code=0,
                         stdout="ok", stderr="", duration_ms=duration_ms)


def _fail(robot: str, duration_ms: float = 10.0) -> CommandResult:
    return CommandResult(robot=robot, command="uptime", exit_code=1,
                         stdout="", stderr="connection refused", duration_ms=duration_ms)


def _healthy(robot: str, host: str = "10.0.0.1") -> RobotHealth:
    return RobotHealth(robot=robot, host=host, status=HealthStatus.HEALTHY,
                       message="Responded in 5ms", duration_ms=5.0)


def _unhealthy(robot: str, host: str = "10.0.0.2") -> RobotHealth:
    return RobotHealth(robot=robot, host=host, status=HealthStatus.UNHEALTHY,
                       message="Connection refused", duration_ms=0.0)


class TestBuildCommandReport:
    def test_all_succeed(self):
        results = [_ok("arm-01"), _ok("arm-02")]
        report = build_command_report("deploy", results, 100.0)
        assert report.total_robots == 2
        assert report.succeeded == 2
        assert report.failed == 0
        assert report.unhealthy_robots == []
        assert report.operation == "deploy"

    def test_partial_failure(self):
        results = [_ok("arm-01"), _fail("arm-02"), _ok("arm-03")]
        report = build_command_report("run", results, 200.0)
        assert report.succeeded == 2
        assert report.failed == 1
        assert "arm-02" in report.unhealthy_robots

    def test_all_fail(self):
        results = [_fail("arm-01"), _fail("arm-02")]
        report = build_command_report("restart", results, 50.0)
        assert report.failed == 2
        assert report.succeeded == 0

    def test_avg_latency(self):
        results = [_ok("r-01", 10.0), _ok("r-02", 30.0)]
        report = build_command_report("run", results, 30.0)
        assert report.avg_latency_ms == 20.0

    def test_results_list_length(self):
        results = [_ok("r-01"), _fail("r-02"), _ok("r-03")]
        report = build_command_report("run", results, 50.0)
        assert len(report.results) == 3

    def test_empty_robots(self):
        report = build_command_report("run", [], 0.0)
        assert report.total_robots == 0
        assert report.succeeded == 0
        assert report.failed == 0

    def test_duration_recorded(self):
        report = build_command_report("run", [_ok("r-01")], 123.4)
        assert report.duration_ms == 123.4


class TestBuildHealthReport:
    def test_all_healthy(self):
        results = [_healthy("arm-01"), _healthy("arm-02")]
        report = build_health_report(results, 50.0)
        assert report.succeeded == 2
        assert report.failed == 0
        assert report.unhealthy_robots == []

    def test_partial_failure(self):
        results = [_healthy("arm-01"), _unhealthy("arm-02")]
        report = build_health_report(results, 50.0)
        assert report.succeeded == 1
        assert report.failed == 1
        assert "arm-02" in report.unhealthy_robots

    def test_operation_name(self):
        report = build_health_report([], 0.0)
        assert report.operation == "health"


class TestFleetReport:
    def test_success_rate_all_succeed(self):
        report = build_command_report("run", [_ok("r-01"), _ok("r-02")], 10.0)
        assert report.success_rate == 1.0

    def test_success_rate_half(self):
        report = build_command_report("run", [_ok("r-01"), _fail("r-02")], 10.0)
        assert report.success_rate == 0.5

    def test_success_rate_empty(self):
        report = build_command_report("run", [], 0.0)
        assert report.success_rate == 0.0

    def test_to_dict_is_json_serializable(self):
        report = build_command_report("deploy", [_ok("r-01"), _fail("r-02")], 75.0)
        d = report.to_dict()
        serialized = json.dumps(d)
        parsed = json.loads(serialized)
        assert parsed["operation"] == "deploy"
        assert parsed["succeeded"] == 1
        assert parsed["failed"] == 1
        assert "success_rate" in parsed
        assert "timestamp" in parsed
        assert "results" in parsed

    def test_to_dict_includes_success_rate(self):
        report = build_command_report("run", [_ok("r-01")], 10.0)
        assert "success_rate" in report.to_dict()

    def test_operation_result_fields(self):
        results = [_ok("r-01", 15.0)]
        report = build_command_report("run", results, 15.0)
        r = report.results[0]
        assert r.robot == "r-01"
        assert r.success is True
        assert r.exit_code == 0
        assert r.duration_ms == 15.0
