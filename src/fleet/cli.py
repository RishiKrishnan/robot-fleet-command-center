from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys

from fleet.config import FleetConfig, load_config
from fleet.executor import MockSSHExecutor, run_fleet_concurrent
from fleet.health import HealthStatus, check_fleet_health
from fleet.logging_config import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "configs/robots.yaml"


def _to_json(data: list) -> str:
    rows = []
    for item in data:
        d = dataclasses.asdict(item)
        # Include derived properties not captured by asdict()
        if hasattr(item, "success"):
            d["success"] = item.success
        rows.append(d)
    return json.dumps(rows, indent=2)


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
    robot_name: str | None = getattr(args, "robot", None)
    tag: str | None = getattr(args, "tag", None)

    if robot_name:
        robots = [r for r in config.robots if r.name == robot_name]
        if not robots:
            print(f"Error: robot '{robot_name}' not found in config.", file=sys.stderr)
            return 1
    elif tag:
        robots = config.filter_by_tag(tag)
        if not robots:
            print(f"No robots matched tag '{tag}'.")
            return 0
    else:
        robots = config.robots

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleet",
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

    # Shared --output flag; added as a parent so it sits after the subcommand
    # (e.g. `fleet list --output json`) rather than before it.
    output_parent = argparse.ArgumentParser(add_help=False)
    output_parent.add_argument(
        "--output",
        "-o",
        choices=["human", "json"],
        default="human",
        help="Output format (default: human)",
    )

    sub.add_parser("list", parents=[output_parent], help="List all configured robots")
    sub.add_parser("health", parents=[output_parent], help="Run health checks on all robots")

    run_p = sub.add_parser(
        "run", parents=[output_parent], help="Execute a command across the fleet"
    )
    run_p.add_argument("shell_command", nargs="+", help="Shell command to execute")
    target = run_p.add_mutually_exclusive_group()
    target.add_argument("--robot", "-r", metavar="NAME", help="Target a single robot by name")
    target.add_argument("--tag", "-t", metavar="TAG", help="Target robots matching a tag")

    return parser


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
    }
    sys.exit(dispatch[args.subcommand](args, config))


if __name__ == "__main__":
    main()
