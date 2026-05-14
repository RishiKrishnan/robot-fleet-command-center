import pytest

from fleet.config import FleetConfig, Robot, load_config


def test_load_config(tmp_path):
    config_file = tmp_path / "robots.yaml"
    config_file.write_text(
        "robots:\n"
        "  - name: arm-01\n"
        "    host: 192.168.1.1\n"
        "    type: arm\n"
        "    tags: [production]\n"
        "  - name: mobile-01\n"
        "    host: 192.168.1.2\n"
        "    type: mobile\n"
        "    tags: [staging]\n"
    )
    config = load_config(config_file)
    assert len(config.robots) == 2
    assert config.robots[0].name == "arm-01"
    assert config.robots[1].type == "mobile"


def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config("/nonexistent/robots.yaml")


def test_load_config_applies_defaults(tmp_path):
    config_file = tmp_path / "robots.yaml"
    config_file.write_text(
        "robots:\n"
        "  - name: r\n"
        "    host: 10.0.0.1\n"
        "    type: arm\n"
    )
    config = load_config(config_file)
    robot = config.robots[0]
    assert robot.port == 22
    assert robot.user == "robot"
    assert robot.tags == []


def test_get_robot_found(two_robots):
    robot = two_robots.get_robot("arm-01")
    assert robot is not None
    assert robot.host == "192.168.10.1"


def test_get_robot_not_found(two_robots):
    assert two_robots.get_robot("does-not-exist") is None


def test_filter_by_tag(two_robots):
    results = two_robots.filter_by_tag("production")
    assert len(results) == 1
    assert results[0].name == "arm-01"


def test_filter_by_tag_no_match(two_robots):
    assert two_robots.filter_by_tag("unknown") == []


def test_filter_by_tag_multiple_matches():
    config = FleetConfig(
        robots=[
            Robot(name="a", host="10.0.0.1", type="arm", tags=["production"]),
            Robot(name="b", host="10.0.0.2", type="arm", tags=["production"]),
            Robot(name="c", host="10.0.0.3", type="mobile", tags=["staging"]),
        ]
    )
    results = config.filter_by_tag("production")
    assert len(results) == 2
