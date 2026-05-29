from fleet.config import Robot
from fleet.executor import CommandResult, MockSSHExecutor, run_fleet_concurrent


def test_successful_execution(arm_robot):
    executor = MockSSHExecutor(latency_ms=0)
    result = executor.run(arm_robot, "echo hello")
    assert result.success
    assert result.exit_code == 0
    assert result.command == "echo hello"
    assert result.robot == arm_robot.name
    assert result.stdout != ""
    assert result.stderr == ""


def test_fail_by_host(arm_robot):
    executor = MockSSHExecutor(fail_hosts={arm_robot.host}, latency_ms=0)
    result = executor.run(arm_robot, "echo hello")
    assert not result.success
    assert result.exit_code == 1
    assert "Connection refused" in result.stderr
    assert result.stdout == ""


def test_fail_by_robot_name(arm_robot):
    executor = MockSSHExecutor(fail_hosts={arm_robot.name}, latency_ms=0)
    result = executor.run(arm_robot, "echo hello")
    assert not result.success


def test_duration_is_recorded(arm_robot):
    executor = MockSSHExecutor(latency_ms=10)
    result = executor.run(arm_robot, "echo hello")
    assert result.duration_ms >= 0


def test_command_result_success_property():
    result = CommandResult(
        robot="r", command="c", exit_code=0, stdout="ok", stderr="", duration_ms=1.0
    )
    assert result.success


def test_command_result_failure_property():
    result = CommandResult(
        robot="r", command="c", exit_code=1, stdout="", stderr="err", duration_ms=1.0
    )
    assert not result.success


def test_no_fail_hosts_by_default(arm_robot):
    executor = MockSSHExecutor(latency_ms=0)
    result = executor.run(arm_robot, "uptime")
    assert result.success


# --- failure_modes ---


def test_failure_mode_unreachable(arm_robot):
    executor = MockSSHExecutor(failure_modes={"arm-01": "unreachable"}, latency_ms=0)
    result = executor.run(arm_robot, "uptime")
    assert not result.success
    assert "Connection refused" in result.stderr


def test_failure_mode_degraded_succeeds(arm_robot):
    executor = MockSSHExecutor(failure_modes={"arm-01": "degraded"}, latency_ms=0)
    result = executor.run(arm_robot, "uptime")
    assert result.success
    assert "WARNING" in result.stderr


def test_failure_mode_deploy_failure(arm_robot):
    executor = MockSSHExecutor(failure_modes={"arm-01": "deploy_failure"}, latency_ms=0)
    result = executor.run(arm_robot, "deploy --version 2.2.0")
    assert not result.success
    assert "incompatible" in result.stderr


def test_failure_mode_deploy_failure_ignores_non_deploy(arm_robot):
    executor = MockSSHExecutor(failure_modes={"arm-01": "deploy_failure"}, latency_ms=0)
    result = executor.run(arm_robot, "uptime")
    assert result.success


def test_ok_response_journalctl(arm_robot):
    executor = MockSSHExecutor(latency_ms=0)
    result = executor.run(arm_robot, "journalctl -u robot-agent -n 50 --no-pager")
    assert result.success
    assert "robot-agent" in result.stdout


def test_ok_response_deploy(arm_robot):
    executor = MockSSHExecutor(latency_ms=0)
    result = executor.run(arm_robot, "deploy --version 2.2.0")
    assert result.success
    assert "extracted" in result.stdout


# --- run_fleet_concurrent ---


def _make_fleet(n: int) -> list[Robot]:
    return [Robot(name=f"r-{i:02d}", host=f"10.0.0.{i}", type="arm") for i in range(n)]


def test_concurrent_all_succeed():
    robots = _make_fleet(4)
    executor = MockSSHExecutor(latency_ms=0)
    results = run_fleet_concurrent(robots, "uptime", executor)
    assert len(results) == 4
    assert all(r.success for r in results)


def test_concurrent_partial_failure():
    robots = _make_fleet(3)
    executor = MockSSHExecutor(fail_hosts={"r-01"}, latency_ms=0)
    results = run_fleet_concurrent(robots, "uptime", executor)
    by_name = {r.robot: r.success for r in results}
    assert by_name["r-00"] is True
    assert by_name["r-01"] is False
    assert by_name["r-02"] is True


def test_concurrent_preserves_order():
    """Results must align with input order regardless of completion order."""
    robots = _make_fleet(5)
    executor = MockSSHExecutor(latency_ms=0)
    results = run_fleet_concurrent(robots, "echo", executor)
    assert [r.robot for r in results] == [rb.name for rb in robots]


def test_concurrent_empty_robots():
    executor = MockSSHExecutor(latency_ms=0)
    assert run_fleet_concurrent([], "uptime", executor) == []


def test_concurrent_executor_raises_captured():
    """An executor that raises must produce a failed result, not propagate."""

    class BoomExecutor:
        def run(self, robot, command):
            raise ConnectionError("timeout")

    robots = _make_fleet(2)
    results = run_fleet_concurrent(robots, "uptime", BoomExecutor())
    assert len(results) == 2
    assert all(not r.success for r in results)
    assert all("timeout" in r.stderr for r in results)


def test_concurrent_respects_max_workers():
    robots = _make_fleet(8)
    executor = MockSSHExecutor(latency_ms=0)
    results = run_fleet_concurrent(robots, "uptime", executor, max_workers=2)
    assert len(results) == 8
    assert all(r.success for r in results)
