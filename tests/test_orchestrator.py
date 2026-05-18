"""Tests for the orchestrator layer."""
from fleet.config import FleetConfig, Robot
from fleet.executor import MockSSHExecutor
from fleet.orchestrator import deploy, fetch_logs, fleet_status, restart
from fleet.telemetry import TelemetrySampler


def _fleet(*names: str) -> FleetConfig:
    robots = [Robot(name=n, host=f"10.0.0.{i}", type="arm") for i, n in enumerate(names, 1)]
    return FleetConfig(robots=robots)


class TestDeploy:
    def test_all_succeed(self):
        config = _fleet("arm-01", "arm-02")
        executor = MockSSHExecutor(latency_ms=0)
        results, duration_ms = deploy(config.robots, "2.2.0", executor)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert duration_ms >= 0

    def test_partial_failure(self):
        config = _fleet("arm-01", "arm-02", "arm-03")
        executor = MockSSHExecutor(latency_ms=0, failure_modes={"arm-02": "deploy_failure"})
        results, _ = deploy(config.robots, "2.2.0", executor)
        by_name = {r.robot: r.success for r in results}
        assert by_name["arm-01"] is True
        assert by_name["arm-02"] is False
        assert by_name["arm-03"] is True

    def test_deploy_command_contains_version(self):
        config = _fleet("arm-01")
        executor = MockSSHExecutor(latency_ms=0)
        results, _ = deploy(config.robots, "2.2.0", executor)
        assert "2.2.0" in results[0].command

    def test_empty_robots(self):
        executor = MockSSHExecutor(latency_ms=0)
        results, duration_ms = deploy([], "2.2.0", executor)
        assert results == []

    def test_unreachable_robot_captured(self):
        config = _fleet("arm-01")
        executor = MockSSHExecutor(latency_ms=0, failure_modes={"arm-01": "unreachable"})
        results, _ = deploy(config.robots, "2.2.0", executor)
        assert not results[0].success


class TestRestart:
    def test_all_succeed(self):
        config = _fleet("arm-01", "mobile-01")
        executor = MockSSHExecutor(latency_ms=0)
        results, duration_ms = restart(config.robots, executor)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_partial_failure(self):
        config = _fleet("arm-01", "arm-02")
        executor = MockSSHExecutor(fail_hosts={"arm-02"}, latency_ms=0)
        results, _ = restart(config.robots, executor)
        by_name = {r.robot: r.success for r in results}
        assert by_name["arm-01"] is True
        assert by_name["arm-02"] is False

    def test_restart_command_targets_correct_service(self):
        config = _fleet("arm-01")
        executor = MockSSHExecutor(latency_ms=0)
        results, _ = restart(config.robots, executor)
        assert "robot-agent" in results[0].command

    def test_duration_is_positive(self):
        config = _fleet("arm-01")
        executor = MockSSHExecutor(latency_ms=0)
        _, duration_ms = restart(config.robots, executor)
        assert duration_ms >= 0


class TestFetchLogs:
    def test_success(self):
        robot = Robot(name="arm-01", host="10.0.0.1", type="arm")
        executor = MockSSHExecutor(latency_ms=0)
        result = fetch_logs(robot, executor)
        assert result.success
        assert result.robot == "arm-01"
        assert "robot-agent" in result.stdout

    def test_lines_param_in_command(self):
        robot = Robot(name="arm-01", host="10.0.0.1", type="arm")
        executor = MockSSHExecutor(latency_ms=0)
        result = fetch_logs(robot, executor, lines=100)
        assert "100" in result.command

    def test_unreachable_robot(self):
        robot = Robot(name="arm-01", host="10.0.0.1", type="arm")
        executor = MockSSHExecutor(fail_hosts={"arm-01"}, latency_ms=0)
        result = fetch_logs(robot, executor)
        assert not result.success


class TestFleetStatus:
    def test_returns_three_components(self):
        config = _fleet("arm-01", "arm-02")
        executor = MockSSHExecutor(latency_ms=0)
        sampler = TelemetrySampler(seed=1)
        health_results, telemetry, duration_ms = fleet_status(config, executor, sampler)
        assert len(health_results) == 2
        assert len(telemetry) == 2
        assert duration_ms >= 0

    def test_health_and_telemetry_cover_same_robots(self):
        config = _fleet("arm-01", "arm-02", "mobile-01")
        executor = MockSSHExecutor(latency_ms=0)
        sampler = TelemetrySampler(seed=0)
        health_results, telemetry, _ = fleet_status(config, executor, sampler)
        health_names = {h.robot for h in health_results}
        telem_names = {t.robot for t in telemetry}
        assert health_names == telem_names

    def test_partial_health_failure_still_returns_full_fleet(self):
        config = _fleet("arm-01", "arm-02")
        executor = MockSSHExecutor(fail_hosts={"arm-01"}, latency_ms=0)
        sampler = TelemetrySampler(seed=0)
        health_results, telemetry, _ = fleet_status(config, executor, sampler)
        assert len(health_results) == 2
        assert len(telemetry) == 2
