# Robot Fleet Command Center

[![CI](https://github.com/RishiKrishnan/robot-fleet-command-center/actions/workflows/ci.yml/badge.svg)](https://github.com/RishiKrishnan/robot-fleet-command-center/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A production-style CLI for orchestrating and monitoring a fleet of robots over SSH.
Built to reflect tooling patterns used in real robotics infrastructure and SRE environments:
concurrent execution, telemetry simulation, structured reporting, and graceful failure handling.

---

## What this demonstrates

| Pattern | Where |
|---|---|
| Concurrent fan-out with `ThreadPoolExecutor` | `executor.py` → `run_fleet_concurrent` |
| Per-robot failure isolation | futures caught individually; fleet continues on partial failures |
| Telemetry simulation with seeded RNG | `telemetry.py` → `TelemetrySampler` |
| Structured JSON reporting | `reporting.py` → `FleetReport` with summary stats |
| Clean orchestration layer | `orchestrator.py` — thin controller, delegates to domain modules |
| Protocol-based executor interface | swap `MockSSHExecutor` for Paramiko without touching business logic |
| `src/` layout with `pyproject.toml` | standard Python packaging |
| Full pytest coverage | 98 tests across 7 test files, 88% line coverage |

---

## Architecture

```
src/fleet/
├── config.py         load_config() → Robot / FleetConfig dataclasses
├── executor.py       Executor Protocol + MockSSHExecutor + run_fleet_concurrent()
├── health.py         check_robot_health() / check_fleet_health() — concurrent
├── telemetry.py      TelemetrySampler — battery, latency, task, health_score
├── orchestrator.py   deploy() / restart() / fetch_logs() / fleet_status()
├── reporting.py      FleetReport — structured summaries with stats
├── cli.py            argparse entry point; dispatches to domain modules
└── logging_config.py timestamped structured logging to stderr

configs/robots.yaml   8-robot fleet definition
tests/                98 pytest tests covering all modules
```

**Data flow (one-way, no cycles):**

```
config ──► executor ──► health   ┐
config ──► telemetry             ├──► orchestrator ──► reporting ──► cli
config ──► executor ──► orchestrator ┘
```

### Why a separate orchestrator?

In real robotics infrastructure a fleet management service sequences multi-step
operations: pre-flight check → concurrent deploy → verify → rollback on failure.
The `orchestrator` layer owns that sequencing and timing context. `executor` and
`health` stay focused on single-robot mechanics and are independently testable.

### Concurrency model

`run_fleet_concurrent` submits one task per robot to a `ThreadPoolExecutor` (capped
at 32 workers). Each future is individually guarded: an exception from any robot
becomes a failed `CommandResult` rather than propagating, so one unreachable robot
never aborts the rest of the fleet. Results are re-assembled in input order via a
`future → index` map, so callers can rely on position-based access.

`check_fleet_health` uses the same pattern — concurrent health checks, failures
captured, results ordered by config.

---

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Commands

```bash
fleetctl list                          # list all configured robots
fleetctl health                        # connectivity health check across fleet
fleetctl status                        # live status: health + telemetry per robot
fleetctl run "uptime"                  # run a command across all robots
fleetctl deploy 2.2.0                  # deploy a software version to the fleet
fleetctl restart                       # restart robot-agent service on fleet
fleetctl logs arm-01                   # fetch logs from a single robot
fleetctl report                        # full structured fleet health report

# Targeting (run / deploy / restart)
fleetctl run --robot arm-01 "uptime"
fleetctl deploy 2.2.0 --tag production

# Output format (most commands)
fleetctl status --output json
fleetctl report --output json

# Logging verbosity
fleetctl --log-level DEBUG health
```

> `fleet` is also available as an alias for `fleetctl`.

---

## Example workflows

### Fleet status

```
$ fleetctl status

ROBOT                STATE        BATT   LATENCY TASK       VER      SCORE
---------------------------------------------------------------------------
arm-01               ONLINE         87%      14ms patrol     2.2.0    0.87
arm-02               ONLINE         74%      31ms idle       2.1.1    0.81
arm-03               DEGRADED       19%     342ms error      2.1.0    0.21
mobile-01            ONLINE         91%       8ms charging   2.2.0    0.93
mobile-02            ONLINE         65%      22ms inspection 2.1.1    0.79
mobile-03            DEGRADED       12%     510ms error      2.1.0    0.18
inspection-01        ONLINE         88%      11ms patrol     2.2.0    0.90
inspection-02        ONLINE         77%      19ms idle       2.2.0    0.84

6 online  2 degraded  0 unreachable  (8 total)
```

### Deploy with partial failure

```
$ fleetctl deploy 2.2.0 --tag production

Deploying version 2.2.0 to 5 robot(s)...

  [arm-01]        OK   deploy: version extracted successfully on arm-01
  [arm-02]        OK   deploy: version extracted successfully on arm-02
  [arm-03]        OK   deploy: version extracted successfully on arm-03
  [mobile-01]     OK   deploy: version extracted successfully on mobile-01
  [inspection-02] FAIL deploy: target version incompatible with installed firmware

  Timestamp   : 2026-05-18T10:02:31Z
  Duration    : 52ms
  Robots      : 5 total  4 succeeded  1 failed
  Success rate: 80%
  Avg latency : 10ms
  Unhealthy   : inspection-02
```

### Structured JSON report

```json
{
  "timestamp": "2026-05-18T10:02:31Z",
  "operation": "health",
  "duration_ms": 12.4,
  "total_robots": 8,
  "succeeded": 8,
  "failed": 0,
  "avg_latency_ms": 0.1,
  "unhealthy_robots": [],
  "success_rate": 1.0,
  "results": [
    {
      "robot": "arm-01",
      "success": true,
      "exit_code": 0,
      "duration_ms": 0.1,
      "message": "Responded in 0ms"
    }
  ]
}
```

### Robot logs

```
$ fleetctl logs arm-01

May 18 10:00:01 arm-01 robot-agent[1234]: INFO  dispatcher started
May 18 10:00:02 arm-01 robot-agent[1234]: INFO  connected to base station
May 18 10:00:15 arm-01 robot-agent[1234]: INFO  task started: patrol
May 18 10:02:30 arm-01 robot-agent[1234]: WARN  battery below 30%
May 18 10:05:00 arm-01 robot-agent[1234]: INFO  task complete, docking
```

---

## Robot configuration

Edit `configs/robots.yaml` to define your fleet:

```yaml
robots:
  - name: arm-01
    host: 192.168.10.1
    type: arm
    port: 22
    user: ubuntu
    tags: [production, arm, zone-a]
```

| Field | Required | Default | Description |
|---|---|---|---|
| `name` | yes | — | Unique robot identifier |
| `host` | yes | — | IP address or hostname |
| `type` | yes | — | Robot class (`arm`, `mobile`, `inspection`) |
| `port` | no | 22 | SSH port |
| `user` | no | `robot` | SSH login user |
| `tags` | no | `[]` | Group labels used by `--tag` filters |

---

## Failure simulation

`MockSSHExecutor` supports per-robot failure modes for realistic scenario testing:

| Mode | Behavior |
|---|---|
| `unreachable` | Connection refused immediately |
| `timeout` | 2-second hang then failure |
| `degraded` | Slow (300ms+) with stderr warnings |
| `deploy_failure` | Non-zero exit on deploy commands |

```python
executor = MockSSHExecutor(
    failure_modes={
        "arm-03":        "degraded",
        "inspection-01": "timeout",
    }
)
```

`TelemetrySampler` supports the same modes for telemetry state:

```python
sampler = TelemetrySampler(
    failure_modes={
        "arm-03":    "degraded",     # low battery, high latency, degraded state
        "mobile-03": "unreachable",  # last_seen stale, health_score 0.0
    }
)
```

---

## Testing

```bash
pytest                                           # 98 tests
pytest tests/test_orchestrator.py               # orchestration layer
pytest tests/test_telemetry.py                  # telemetry simulation
pytest tests/test_reporting.py                  # fleet reports
pytest --cov=fleet --cov-report=term-missing    # with coverage
ruff check src/ tests/                          # lint
ruff format --check src/ tests/                 # formatting
```

All tests use `MockSSHExecutor` — no real SSH connections or hardware required.

---

## Quality gates

Every PR is gated by GitHub Actions (`.github/workflows/ci.yml`) on the following:

| Check | Tool | Failure condition |
|---|---|---|
| Lint | `ruff check` | Any lint rule violation in `src/` or `tests/` |
| Formatting | `ruff format --check` | Any file not matching the formatter's canonical output |
| Tests | `pytest --cov=fleet` | Any test failure, **or** total coverage below 85% (`fail_under` in `pyproject.toml`) |
| Compatibility | matrix | Any of the above failing on Python 3.10, 3.11, or 3.12 |

Coverage threshold is set just below current (88%) so trivial refactors don't break the build but meaningful regressions do. Raise it as coverage improves; never silently lower it.

---

## Extending to real hardware

The `Executor` Protocol is the only seam you need to replace:

```python
import paramiko
from fleet.executor import CommandResult
from fleet.config import Robot

class ParamikoExecutor:
    def run(self, robot: Robot, command: str) -> CommandResult:
        # connect via paramiko, run command, return CommandResult
        ...
```

Pass it anywhere `MockSSHExecutor` is used today — no other changes required.
