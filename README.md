# Robot Fleet Command Center

A production-style CLI tool for orchestrating and monitoring a fleet of robots over SSH.

Built to demonstrate reliability engineering patterns applied to robotics infrastructure:
fleet health monitoring, parallel command dispatch, declarative YAML configuration,
structured logging, and a fully tested mock execution layer.

---

## Features

- **Fleet health checks** — ping every robot and report connectivity status at a glance
- **Remote command execution** — run shell commands across the whole fleet, a single robot,
  or a tagged group
- **YAML-driven configuration** — define robots declaratively; no code changes to add or
  remove nodes
- **Swappable executor** — `MockSSHExecutor` runs without hardware; replace with a
  Paramiko-backed implementation by satisfying the same `Executor` protocol
- **Structured logging** — configurable verbosity with ISO timestamps, written to stderr so
  stdout stays pipeline-friendly

---

## Quick Start

**Requirements:** Python 3.10+

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# List configured robots
fleet list

# Check fleet health
fleet health

# Run a command on all robots
fleet run "systemctl status ros2"

# Target by tag or name
fleet run --tag production "uptime"
fleet run --robot arm-01 "hostname"
```

---

## Example Output

```
$ fleet list
NAME                 HOST               TYPE         TAGS
--------------------------------------------------------------------
arm-01               192.168.10.1       arm          production, arm
arm-02               192.168.10.2       arm          production, arm
mobile-01            192.168.10.11      mobile       production, mobile
mobile-02            192.168.10.12      mobile       staging, mobile
inspection-01        192.168.10.21      inspection   staging, inspection

$ fleet health

ROBOT                HOST               STATUS       MESSAGE
------------------------------------------------------------------------
arm-01               192.168.10.1       HEALTHY      Responded in 0ms
arm-02               192.168.10.2       HEALTHY      Responded in 0ms
mobile-01            192.168.10.11      HEALTHY      Responded in 0ms
mobile-02            192.168.10.12      HEALTHY      Responded in 0ms
inspection-01        192.168.10.21      HEALTHY      Responded in 0ms

5/5 robots healthy

$ fleet run --tag production "uptime"
[arm-01] OK
[arm-02] OK
[mobile-01] OK
```

---

## Robot Configuration

Edit `configs/robots.yaml` to define your fleet:

```yaml
robots:
  - name: arm-01
    host: 192.168.10.1
    type: arm
    port: 22
    user: ubuntu
    tags: [production, arm]
```

| Field  | Required | Default  | Description                        |
|--------|----------|----------|------------------------------------|
| name   | yes      | —        | Unique identifier                  |
| host   | yes      | —        | IP address or hostname             |
| type   | yes      | —        | Robot class (arm, mobile, etc.)    |
| port   | no       | 22       | SSH port                           |
| user   | no       | robot    | SSH user                           |
| tags   | no       | []       | Used for group targeting with --tag |

---

## Architecture

```
src/fleet/
├── config.py        # YAML loading → Robot / FleetConfig dataclasses
├── executor.py      # Executor protocol + MockSSHExecutor
├── health.py        # Health check logic on top of Executor
├── cli.py           # argparse entry point; dispatches to above modules
└── logging_config.py
```

The `Executor` [Protocol](src/fleet/executor.py) is the key seam in the design. `health.py`
and `cli.py` call `executor.run(robot, command)` and know nothing about how that's
implemented — making it straightforward to swap in a Paramiko SSH executor, a dry-run
logger, or a parallel executor without touching any business logic.

Data flows one way: `config` has no knowledge of `executor` or `health`; `executor` knows
only `Robot`; `health` composes `config` + `executor`; `cli` wires everything together.

---

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=fleet --cov-report=term-missing

# Run a single test file
pytest tests/test_health.py

# Run a single test
pytest tests/test_health.py::test_executor_exception_yields_unknown
```

Tests use `MockSSHExecutor` throughout — no real SSH connections, no hardware required.
The `BrokenExecutor` fixture in `test_health.py` verifies that executor-level exceptions
are caught and reported as `UNKNOWN` status rather than propagated.

---

## CI

GitHub Actions runs lint (`ruff`) and the full test suite on Python 3.10, 3.11, and 3.12
on every push and pull request. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Extending

**Add real SSH execution:** implement a class with
`def run(self, robot: Robot, command: str) -> CommandResult` using Paramiko, then pass it
anywhere a `MockSSHExecutor` is used today.

**Add parallel execution:** wrap `check_fleet_health` or `cmd_run` with
`concurrent.futures.ThreadPoolExecutor` — the per-robot functions are already independent.

**Add new CLI commands:** add a `sub.add_parser(...)` block in `build_parser()` and a
matching `cmd_*` function, then register it in the `dispatch` dict in `main()`.
