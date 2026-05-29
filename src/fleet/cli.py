"""fleetctl — Robot Fleet Command Center CLI.

Entry point for all fleet operations. Each subcommand delegates to the
appropriate domain module (orchestrator, health, reporting) and handles
only I/O: argument parsing, output formatting, and exit codes.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
import time

from fleet.config import FleetConfig, Robot, load_config
from fleet.executor import MockSSHExecutor, run_fleet_concurrent
from fleet.health import HealthStatus, check_fleet_health
from fleet.logging_config import setup_logging
from fleet.orchestrator import deploy, fetch_logs, fleet_status, restart
from fleet.reporting import FleetReport, build_command_report, build_health_report
from fleet.telemetry import TelemetrySampler

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "configs/robots.yaml"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _to_json(data: list) -> str:
    """Serialize a list of dataclasses (or dicts) to indented JSON."""
    rows = []
    for item in data:
        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            d = dataclasses.asdict(item)
            if hasattr(item, "success"):
                d["success"] = item.success
            rows.append(d)
        else:
            rows.append(item)
    return json.dumps(rows, indent=2)


def _filter_robots(
    args: argparse.Namespace,
    config: FleetConfig,
) -> list[Robot] | None:
    """Return the target robot list based on --robot / --tag flags.

    Returns None on error (caller should exit 1).
    Returns an empty list when --tag matches nothing (caller should exit 0).
    """
    robot_name: str | None = getattr(args, "robot", None)
    tag: str | None = getattr(args, "tag", None)

    if robot_name:
        robots = [r for r in config.robots if r.name == robot_name]
        if not robots:
            print(f"Error: robot '{robot_name}' not found in config.", file=sys.stderr)
            return None
        return robots

    if tag:
        robots = config.filter_by_tag(tag)
        if not robots:
            print(f"No robots matched tag '{tag}'.")
            return []
        return robots

    return config.robots


def _print_report_summary(report: FleetReport) -> None:
    print(f"\n  Timestamp   : {report.timestamp}")
    print(f"  Duration    : {report.duration_ms:.0f}ms")
    print(
        f"  Robots      : {report.total_robots} total  "
        f"{report.succeeded} succeeded  {report.failed} failed"
    )
    print(f"  Success rate: {report.success_rate:.0%}")
    print(f"  Avg latency : {report.avg_latency_ms:.0f}ms")
    if report.unhealthy_robots:
        print(f"  Unhealthy   : {', '.join(report.unhealthy_robots)}")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace, config: FleetConfig) -> int:
    if args.output == "json":
        print(_to_json(config.robots))
        return 0

    print(f"{'NAME':<20} {'HOST':<18} {'TYPE':<12} TAGS")
    print("-" * 68)
    for robot in config.robots:
        tags = ", ".join(robot.tags) if robot.tags else "-"
        print(f"{robot.name:<20} {robot.host:<18} {robot.type:<12} {tags}")
    return 0


def cmd_health(args: argparse.Namespace, config: FleetConfig) -> int:
    executor = MockSSHExecutor(latency_ms=0)
    results = check_fleet_health(config, executor)
    healthy = sum(1 for h in results if h.status == HealthStatus.HEALTHY)

    if args.output == "json":
        print(_to_json(results))
        return 0 if healthy == len(results) else 1

    print(f"\n{'ROBOT':<20} {'HOST':<18} {'STATUS':<12} MESSAGE")
    print("-" * 72)
    for h in results:
        print(f"{h.robot:<20} {h.host:<18} {h.status.value.upper():<12} {h.message}")
    print(f"\n{healthy}/{len(results)} robots healthy")
    return 0 if healthy == len(results) else 1


def cmd_run(args: argparse.Namespace, config: FleetConfig) -> int:
    command = " ".join(args.shell_command)
    robots = _filter_robots(args, config)
    if robots is None:
        return 1
    if not robots:
        return 0

    executor = MockSSHExecutor()
    results = run_fleet_concurrent(robots, command, executor)

    if args.output == "json":
        print(_to_json(results))
    else:
        for result in results:
            if result.success:
                print(f"[{result.robot}] OK")
            else:
                print(f"[{result.robot}] FAIL  {result.stderr}")

    failed = sum(1 for r in results if not r.success)
    return 0 if failed == 0 else 1


def cmd_status(args: argparse.Namespace, config: FleetConfig) -> int:
    """Show live fleet status: connectivity health + telemetry per robot."""
    executor = MockSSHExecutor(latency_ms=0)
    sampler = TelemetrySampler()
    health_results, telemetry_list, _ = fleet_status(config, executor, sampler)

    telem = {t.robot: t for t in telemetry_list}

    if args.output == "json":
        combined = []
        for h in health_results:
            t = telem.get(h.robot)
            row: dict = {"robot": h.robot, "host": h.host, "health": h.status.value}
            if t:
                row.update(dataclasses.asdict(t))
            combined.append(row)
        print(json.dumps(combined, indent=2))
        return 0

    header = f"{'ROBOT':<20} {'STATE':<12} {'BATT':>6} {'LATENCY':>9} {'TASK':<10} {'VER':<8} SCORE"
    print(f"\n{header}")
    print("-" * len(header))
    for h in health_results:
        t = telem.get(h.robot)
        if t:
            state = t.operational_state.upper()
            batt = f"{t.battery_pct:.0f}%"
            lat = f"{t.latency_ms:.0f}ms"
            task = t.current_task[:10]
            ver = t.software_version
            score = f"{t.health_score:.2f}"
        else:
            state = h.status.value.upper()
            batt = lat = task = ver = score = "?"
        print(f"{h.robot:<20} {state:<12} {batt:>6} {lat:>9} {task:<10} {ver:<8} {score}")

    online = sum(1 for t in telemetry_list if t.operational_state == "online")
    degraded = sum(1 for t in telemetry_list if t.operational_state == "degraded")
    unreachable = sum(1 for t in telemetry_list if t.operational_state == "unreachable")
    total = len(telemetry_list)
    print(f"\n{online} online  {degraded} degraded  {unreachable} unreachable  ({total} total)")
    return 0


def cmd_deploy(args: argparse.Namespace, config: FleetConfig) -> int:
    """Deploy a software version to the fleet (or a subset)."""
    robots = _filter_robots(args, config)
    if robots is None:
        return 1
    if not robots:
        return 0

    executor = MockSSHExecutor(latency_ms=0)
    results, duration_ms = deploy(robots, args.version, executor)
    report = build_command_report("deploy", results, duration_ms)

    if args.output == "json":
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.failed == 0 else 1

    print(f"\nDeploying version {args.version} to {len(robots)} robot(s)...\n")
    for r in results:
        status = "OK  " if r.success else "FAIL"
        detail = r.stderr if not r.success else r.stdout[:60]
        print(f"  [{r.robot}] {status}  {detail}")
    _print_report_summary(report)
    return 0 if report.failed == 0 else 1


def cmd_restart(args: argparse.Namespace, config: FleetConfig) -> int:
    """Restart the robot-agent service across the fleet (or a subset)."""
    robots = _filter_robots(args, config)
    if robots is None:
        return 1
    if not robots:
        return 0

    executor = MockSSHExecutor(latency_ms=0)
    results, duration_ms = restart(robots, executor)
    report = build_command_report("restart", results, duration_ms)

    if args.output == "json":
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.failed == 0 else 1

    print(f"\nRestarting robot-agent on {len(robots)} robot(s)...\n")
    for r in results:
        status = "OK  " if r.success else "FAIL"
        detail = r.stderr if not r.success else ""
        print(f"  [{r.robot}] {status}  {detail}".rstrip())
    _print_report_summary(report)
    return 0 if report.failed == 0 else 1


def cmd_logs(args: argparse.Namespace, config: FleetConfig) -> int:
    """Fetch recent logs from a single robot."""
    robot = config.get_robot(args.robot_name)
    if not robot:
        print(f"Error: robot '{args.robot_name}' not found in config.", file=sys.stderr)
        return 1

    executor = MockSSHExecutor(latency_ms=0)
    result = fetch_logs(robot, executor, lines=args.lines)
    print(result.stdout if result.success else result.stderr)
    return 0 if result.success else 1


def cmd_report(args: argparse.Namespace, config: FleetConfig) -> int:
    """Generate a full structured fleet health report."""
    executor = MockSSHExecutor(latency_ms=0)
    start = time.monotonic()
    health_results = check_fleet_health(config, executor)
    duration_ms = (time.monotonic() - start) * 1000
    report = build_health_report(health_results, duration_ms)

    if args.output == "json":
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.failed == 0 else 1

    print("\n=== Fleet Health Report ===")
    _print_report_summary(report)
    print(f"\n{'ROBOT':<20} {'STATUS':<10} {'LATENCY':>9} MESSAGE")
    print("-" * 72)
    for r in report.results:
        status = "HEALTHY" if r.success else "UNHEALTHY"
        print(f"{r.robot:<20} {status:<10} {r.duration_ms:>8.0f}ms {r.message}")
    return 0 if report.failed == 0 else 1


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleetctl",
        description="Robot Fleet Command Center — orchestrate and monitor your robot fleet.",
    )
    parser.add_argument(
        "--config",
        "-c",
        default=DEFAULT_CONFIG,
        metavar="PATH",
        help=f"Path to robot config YAML (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )

    sub = parser.add_subparsers(dest="subcommand", metavar="COMMAND")
    sub.required = True

    # Shared parent: --output flag
    output_p = argparse.ArgumentParser(add_help=False)
    output_p.add_argument(
        "--output",
        "-o",
        choices=["human", "json"],
        default="human",
        help="Output format (default: human)",
    )

    # Shared parent: --robot / --tag filter
    target_p = argparse.ArgumentParser(add_help=False)
    grp = target_p.add_mutually_exclusive_group()
    grp.add_argument("--robot", "-r", metavar="NAME", help="Target a single robot by name")
    grp.add_argument("--tag", "-t", metavar="TAG", help="Target robots matching a tag")

    # --- list ---
    sub.add_parser(
        "list",
        parents=[output_p],
        help="List all configured robots",
    )

    # --- health ---
    sub.add_parser(
        "health",
        parents=[output_p],
        help="Run connectivity health checks on the fleet",
    )

    # --- status ---
    sub.add_parser(
        "status",
        parents=[output_p],
        help="Show live fleet status: health + telemetry",
    )

    # --- run ---
    run_p = sub.add_parser(
        "run",
        parents=[output_p, target_p],
        help="Execute an arbitrary shell command across the fleet",
    )
    run_p.add_argument("shell_command", nargs="+", help="Shell command to execute")

    # --- deploy ---
    deploy_p = sub.add_parser(
        "deploy",
        parents=[output_p, target_p],
        help="Deploy a software version to the fleet",
    )
    deploy_p.add_argument("version", help="Version string to deploy (e.g. 2.2.0)")

    # --- restart ---
    sub.add_parser(
        "restart",
        parents=[output_p, target_p],
        help="Restart the robot-agent service on the fleet",
    )

    # --- logs ---
    logs_p = sub.add_parser(
        "logs",
        help="Fetch recent logs from a single robot",
    )
    logs_p.add_argument("robot_name", metavar="ROBOT", help="Robot name")
    logs_p.add_argument(
        "--lines",
        "-n",
        type=int,
        default=50,
        help="Number of log lines to fetch (default: 50)",
    )

    # --- report ---
    sub.add_parser(
        "report",
        parents=[output_p],
        help="Generate a full structured fleet health report",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.log_level)

    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Failed to load config")
        print(f"Error loading config: {exc}", file=sys.stderr)
        sys.exit(1)

    dispatch = {
        "list": cmd_list,
        "health": cmd_health,
        "run": cmd_run,
        "status": cmd_status,
        "deploy": cmd_deploy,
        "restart": cmd_restart,
        "logs": cmd_logs,
        "report": cmd_report,
    }
    sys.exit(dispatch[args.subcommand](args, config))


if __name__ == "__main__":
    main()
