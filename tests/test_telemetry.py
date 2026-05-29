"""Tests for TelemetrySampler and RobotTelemetry."""

from fleet.config import Robot
from fleet.telemetry import RobotTelemetry, TelemetrySampler


def _robot(name: str = "r-01", host: str = "10.0.0.1") -> Robot:
    return Robot(name=name, host=host, type="arm")


class TestTelemetrySampler:
    def test_sample_returns_telemetry(self):
        sampler = TelemetrySampler(seed=42)
        t = sampler.sample(_robot())
        assert isinstance(t, RobotTelemetry)
        assert t.robot == "r-01"
        assert t.host == "10.0.0.1"

    def test_sample_is_deterministic_with_seed(self):
        sampler = TelemetrySampler(seed=99)
        robot = _robot()
        t1 = sampler.sample(robot)
        t2 = sampler.sample(robot)
        assert t1.battery_pct == t2.battery_pct
        assert t1.latency_ms == t2.latency_ms
        assert t1.health_score == t2.health_score

    def test_different_robots_differ(self):
        sampler = TelemetrySampler(seed=0)
        r1 = sampler.sample(_robot("arm-01", "10.0.0.1"))
        r2 = sampler.sample(_robot("mobile-02", "10.0.0.2"))
        # Names hash differently — at least one field should differ
        assert r1.robot != r2.robot
        assert r1 != r2

    def test_healthy_robot_fields_in_range(self):
        sampler = TelemetrySampler(seed=7)
        t = sampler.sample(_robot())
        assert 0.0 <= t.battery_pct <= 100.0
        assert t.latency_ms >= 0
        assert 0.0 <= t.health_score <= 1.0
        assert t.operational_state in {"online", "degraded", "unreachable"}
        assert t.software_version != ""
        assert t.last_seen != ""
        assert t.current_task != ""

    def test_unreachable_failure_mode(self):
        sampler = TelemetrySampler(failure_modes={"r-01": "unreachable"})
        t = sampler.sample(_robot())
        assert t.operational_state == "unreachable"
        assert t.health_score == 0.0
        assert t.battery_pct == 0.0

    def test_degraded_failure_mode(self):
        sampler = TelemetrySampler(failure_modes={"r-01": "degraded"}, seed=1)
        t = sampler.sample(_robot())
        assert t.operational_state == "degraded"
        assert t.battery_pct < 30.0
        assert t.latency_ms > 100.0

    def test_timeout_failure_mode(self):
        sampler = TelemetrySampler(failure_modes={"r-01": "timeout"}, seed=1)
        t = sampler.sample(_robot())
        assert t.operational_state == "degraded"
        assert t.latency_ms > 1000.0

    def test_failure_mode_by_host(self):
        sampler = TelemetrySampler(failure_modes={"10.0.0.1": "unreachable"})
        t = sampler.sample(_robot("arm-01", "10.0.0.1"))
        assert t.operational_state == "unreachable"

    def test_sample_fleet_covers_all_robots(self):
        robots = [
            _robot("arm-01", "10.0.0.1"),
            _robot("arm-02", "10.0.0.2"),
            _robot("mobile-01", "10.0.0.3"),
        ]
        sampler = TelemetrySampler(seed=5)
        results = sampler.sample_fleet(robots)
        assert len(results) == 3
        assert [t.robot for t in results] == ["arm-01", "arm-02", "mobile-01"]

    def test_is_healthy_property(self):
        sampler = TelemetrySampler(failure_modes={"r-01": "unreachable"})
        t = sampler.sample(_robot())
        assert not t.is_healthy

    def test_healthy_online_robot_is_healthy(self):
        # Force a high-score scenario by using a seed that yields good telemetry
        sampler = TelemetrySampler(seed=100)
        for seed in range(200):
            sampler = TelemetrySampler(seed=seed)
            t = sampler.sample(_robot())
            if t.operational_state == "online" and t.health_score >= 0.7:
                assert t.is_healthy
                break
