from __future__ import annotations

import argparse
import logging
import sys

from fleet.config import FleetConfig, load_config
from fleet.executor import MockSSHExecutor
from fleet.health import HealthStatus, check_fleet_health
from fleet.logging_config import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "configs/robots.yaml"


def cmd_list(args: argparse.Namespace, config: FleetConfig) -> int:
    print(f"{'NAME':<20} {'HOST':<18} {'TYPE':<12} TAGS")
    print("-" * 68)
    for robot in config.robots:
        tags = ", ".join(robot.tags) if robot.tags else "-"
        print(f"{robot.name:<20} {robot.host:<18} {robot.type:<12} {tags}")
    return 0


def cmd_health(args: argparse.Namespace, config: FleetConfig) -> int:
    executor = MockSSHExecutor(latency_ms=0)
    results = check_fleet_health(config, executor)

    print(f"\n{'ROBOT':<20} {'HOST':<18} {'STATUS':<12} MESSAGE")
    print("-" * 72)
    for h in results:
        print(f"{h.robot:<20} {h.host:<18} {h.status.value.upper():<12} {h.message}")

    healthy = sum(1 for h in results if h.status == HealthStatus.HEALTHY)
    total = len(results)
    print(f"\n{healthy}/{total} robots healthy")
    return 0 if healthy == total else 1


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
    failed = 0
    for robot in robots:
        result = executor.run(robot, command)
        if result.success:
            print(f"[{robot.name}] OK")
        else:
            print(f"[{robot.name}] FAIL  {result.stderr}")
            failed += 1

    return 0 if failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleet",
        description="Robot Fleet Command Center — orchestrate and monitor your robot fleet.",
    )
    parser.add_argument(
        "--config", "-c",
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

    sub.add_parser("list", help="List all configured robots")
    sub.add_parser("health", help="Run health checks on all robots")

    run_p = sub.add_parser("run", help="Execute a command across the fleet")
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
