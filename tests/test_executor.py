from fleet.executor import CommandResult, MockSSHExecutor


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
