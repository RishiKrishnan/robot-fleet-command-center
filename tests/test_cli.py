"""Tests for CLI command handlers: JSON output, human output, exit codes."""
import argparse
import json
from unittest.mock import patch

import pytest

from fleet.cli import (
    cmd_deploy,
    cmd_health,
    cmd_list,
    cmd_logs,
    cmd_report,
    cmd_restart,
    cmd_run,
    cmd_status,
)
from fleet.config import FleetConfig, Robot
from fleet.executor import MockSSHExecutor


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


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

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
    broken_fleet = FleetConfig(
        robots=[Robot(name="broken", host="10.0.0.99", type="arm")]
    )
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


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

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


def test_run_unknown_robot_returns_error(fleet, capsys):
    rc = cmd_run(_args(shell_command=["uptime"], robot="no-such-robot"), fleet)
    assert rc == 1


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_json_valid(fleet, capsys):
    rc = cmd_status(_args(output="json"), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert len(data) == 2
    assert "robot" in data[0]
    assert "operational_state" in data[0]
    assert "battery_pct" in data[0]
    assert "health_score" in data[0]


def test_status_human_contains_headers(fleet, capsys):
    cmd_status(_args(), fleet)
    out = capsys.readouterr().out
    assert "ROBOT" in out
    assert "STATE" in out
    assert "BATT" in out


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------

def test_deploy_json_valid(fleet, capsys):
    rc = cmd_deploy(_args(output="json", version="2.2.0"), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["operation"] == "deploy"
    assert data["total_robots"] == 2
    assert data["succeeded"] == 2
    assert "results" in data
    assert "success_rate" in data


def test_deploy_partial_failure_exit_code(capsys):
    partial_fleet = FleetConfig(
        robots=[
            Robot(name="arm-01", host="192.168.10.1", type="arm"),
            Robot(name="broken", host="10.0.0.99", type="arm"),
        ]
    )
    with patch("fleet.cli.MockSSHExecutor") as MockExec:
        MockExec.return_value = MockSSHExecutor(fail_hosts={"broken"}, latency_ms=0)
        rc = cmd_deploy(_args(output="json", version="2.2.0"), partial_fleet)

    assert rc == 1


def test_deploy_human_output(fleet, capsys):
    cmd_deploy(_args(version="2.2.0"), fleet)
    out = capsys.readouterr().out
    assert "2.2.0" in out
    assert "arm-01" in out


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------

def test_restart_json_valid(fleet, capsys):
    rc = cmd_restart(_args(output="json"), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["operation"] == "restart"
    assert data["succeeded"] == 2
    assert data["failed"] == 0


def test_restart_human_output(fleet, capsys):
    cmd_restart(_args(), fleet)
    out = capsys.readouterr().out
    assert "arm-01" in out
    assert "mobile-01" in out


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

def test_logs_success(fleet, capsys):
    rc = cmd_logs(_args(robot_name="arm-01", lines=50), fleet)
    out = capsys.readouterr().out
    assert rc == 0
    assert "robot-agent" in out


def test_logs_unknown_robot(fleet, capsys):
    rc = cmd_logs(_args(robot_name="does-not-exist", lines=50), fleet)
    assert rc == 1


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def test_report_json_valid(fleet, capsys):
    rc = cmd_report(_args(output="json"), fleet)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["operation"] == "health"
    assert data["total_robots"] == 2
    assert "succeeded" in data
    assert "failed" in data
    assert "avg_latency_ms" in data
    assert "unhealthy_robots" in data
    assert "results" in data
    assert "success_rate" in data


def test_report_human_output(fleet, capsys):
    cmd_report(_args(), fleet)
    out = capsys.readouterr().out
    assert "Fleet Health Report" in out
    assert "arm-01" in out


def test_report_unhealthy_exit_code(capsys):
    broken_fleet = FleetConfig(
        robots=[Robot(name="broken", host="10.0.0.99", type="arm")]
    )
    with patch("fleet.cli.MockSSHExecutor") as MockExec:
        MockExec.return_value = MockSSHExecutor(fail_hosts={"broken"}, latency_ms=0)
        rc = cmd_report(_args(output="json"), broken_fleet)
    assert rc == 1
