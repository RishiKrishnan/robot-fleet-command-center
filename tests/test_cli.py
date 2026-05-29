"""Tests for CLI JSON output and backward-compatible human output."""

import argparse
import json

import pytest

from fleet.cli import cmd_health, cmd_list, cmd_run
from fleet.config import FleetConfig, Robot


@pytest.fixture
def fleet() -> FleetConfig:
    return FleetConfig(
        robots=[
            Robot(name="arm-01", host="192.168.10.1", type="arm", tags=["production"]),
            Robot(name="mobile-01", host="192.168.10.11", type="mobile", tags=["staging"]),
        ]
    )


def _args(**kwargs) -> argparse.Namespace:
    defaults = {"output": "human", "robot": None, "tag": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# --- list ---


def test_list_json_valid(fleet, capsys):
    rc = cmd_list(_args(output="json"), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert len(data) == 2
    assert data[0]["name"] == "arm-01"
    assert data[0]["host"] == "192.168.10.1"
    assert data[0]["type"] == "arm"
    assert data[0]["tags"] == ["production"]
    assert data[0]["port"] == 22
    assert data[0]["user"] == "robot"


def test_list_human_unchanged(fleet, capsys):
    rc = cmd_list(_args(), fleet)
    out = capsys.readouterr().out
    assert rc == 0
    assert "NAME" in out
    assert "arm-01" in out


# --- health ---


def test_health_json_valid(fleet, capsys):
    rc = cmd_health(_args(output="json"), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert len(data) == 2
    assert data[0]["robot"] == "arm-01"
    assert data[0]["status"] == "healthy"
    assert "duration_ms" in data[0]
    assert "message" in data[0]


def test_health_json_unhealthy_exit_code(capsys):
    from unittest.mock import patch

    from fleet.executor import MockSSHExecutor

    broken_fleet = FleetConfig(robots=[Robot(name="broken", host="10.0.0.99", type="arm")])
    with patch("fleet.cli.MockSSHExecutor") as MockExec:
        MockExec.return_value = MockSSHExecutor(fail_hosts={"broken"}, latency_ms=0)
        rc = cmd_health(_args(output="json"), broken_fleet)

    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 1
    assert data[0]["status"] == "unhealthy"


def test_health_human_unchanged(fleet, capsys):
    cmd_health(_args(), fleet)
    out = capsys.readouterr().out
    assert "ROBOT" in out
    assert "HEALTHY" in out
    assert "robots healthy" in out


# --- run ---


def test_run_json_valid(fleet, capsys):
    rc = cmd_run(_args(output="json", shell_command=["uptime"]), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert len(data) == 2
    assert data[0]["robot"] == "arm-01"
    assert data[0]["command"] == "uptime"
    assert data[0]["exit_code"] == 0
    assert data[0]["success"] is True
    assert "stdout" in data[0]
    assert "stderr" in data[0]
    assert "duration_ms" in data[0]


def test_run_json_partial_failure_exit_code(capsys):
    from unittest.mock import patch

    from fleet.executor import MockSSHExecutor

    partial_fleet = FleetConfig(
        robots=[
            Robot(name="arm-01", host="192.168.10.1", type="arm"),
            Robot(name="broken", host="10.0.0.99", type="arm"),
        ]
    )
    with patch("fleet.cli.MockSSHExecutor") as MockExec:
        MockExec.return_value = MockSSHExecutor(fail_hosts={"broken"}, latency_ms=0)
        rc = cmd_run(_args(output="json", shell_command=["uptime"]), partial_fleet)

    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 1
    successes = [d["success"] for d in data]
    assert True in successes
    assert False in successes


def test_run_json_tag_filter(fleet, capsys):
    rc = cmd_run(_args(output="json", shell_command=["uptime"], tag="production"), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert len(data) == 1
    assert data[0]["robot"] == "arm-01"


def test_run_human_unchanged(fleet, capsys):
    rc = cmd_run(_args(shell_command=["uptime"]), fleet)
    out = capsys.readouterr().out
    assert rc == 0
    assert "[arm-01] OK" in out
    assert "[mobile-01] OK" in out
