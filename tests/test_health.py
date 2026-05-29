from fleet.config import Robot
from fleet.executor import MockSSHExecutor
from fleet.health import HealthStatus, check_fleet_health, check_robot_health


def test_healthy_robot(arm_robot):
    executor = MockSSHExecutor(latency_ms=0)
    health = check_robot_health(arm_robot, executor)
    assert health.status == HealthStatus.HEALTHY
    assert health.robot == arm_robot.name
    assert health.host == arm_robot.host
    assert "ms" in health.message


def test_unhealthy_robot(arm_robot):
    executor = MockSSHExecutor(fail_hosts={arm_robot.host}, latency_ms=0)
    health = check_robot_health(arm_robot, executor)
    assert health.status == HealthStatus.UNHEALTHY
    assert "Connection refused" in health.message


def test_unhealthy_by_name(arm_robot):
    executor = MockSSHExecutor(fail_hosts={arm_robot.name}, latency_ms=0)
    health = check_robot_health(arm_robot, executor)
    assert health.status == HealthStatus.UNHEALTHY


def test_fleet_health_all_healthy(two_robots):
    executor = MockSSHExecutor(latency_ms=0)
    results = check_fleet_health(two_robots, executor)
    assert len(results) == len(two_robots.robots)
    assert all(h.status == HealthStatus.HEALTHY for h in results)


def test_fleet_health_partial_failure(two_robots):
    executor = MockSSHExecutor(fail_hosts={"arm-01"}, latency_ms=0)
    results = check_fleet_health(two_robots, executor)
    by_name = {h.robot: h.status for h in results}
    assert by_name["arm-01"] == HealthStatus.UNHEALTHY
    assert by_name["mobile-01"] == HealthStatus.HEALTHY


def test_fleet_health_covers_all_robots(two_robots):
    executor = MockSSHExecutor(latency_ms=0)
    results = check_fleet_health(two_robots, executor)
    result_names = {h.robot for h in results}
    config_names = {r.name for r in two_robots.robots}
    assert result_names == config_names


def test_executor_exception_yields_unknown():
    """An executor that raises should return UNKNOWN, not propagate."""

    class BrokenExecutor:
        def run(self, robot, command):
            raise RuntimeError("connection timeout")

    robot = Robot(name="test", host="10.0.0.1", type="arm")
    health = check_robot_health(robot, BrokenExecutor())
    assert health.status == HealthStatus.UNKNOWN
    assert "connection timeout" in health.message
