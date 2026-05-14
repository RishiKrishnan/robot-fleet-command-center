# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Robot Fleet Command Center — a Python CLI tool for orchestrating and health-checking a fleet of robots over SSH. Stack: Python 3.11+, PyYAML, pytest, ruff, GitHub Actions CI.

## Commands

```bash
pip install -e ".[dev]"          # install with dev deps (pytest, ruff)
fleet list                        # list configured robots
fleet health                      # check fleet health
fleet run "uptime"                # run command on all robots
fleet run --tag production "uptime"
fleet run --robot arm-01 "uptime"

pytest                            # run all tests
pytest tests/test_health.py       # single file
pytest tests/test_health.py::test_healthy_robot  # single test
pytest --cov=fleet --cov-report=term-missing
ruff check src/ tests/            # lint
```

## Architecture

```
src/fleet/
├── config.py        # load_config() → Robot / FleetConfig dataclasses
├── executor.py      # Executor protocol + MockSSHExecutor
├── health.py        # check_robot_health / check_fleet_health
├── cli.py           # argparse entry point; dispatches to above modules
└── logging_config.py
configs/robots.yaml  # declarative fleet definition
tests/               # pytest; conftest.py defines shared Robot/FleetConfig fixtures
```

The `Executor` Protocol in `executor.py` is the main extension point — `health.py` and `cli.py` depend on it, not on `MockSSHExecutor` directly. Swap in a Paramiko-backed class without touching business logic. Data flows one way: `config` → `executor` → `health` → `cli`.

---

## Project Philosophy

This project should reflect production-style engineering practices used in robotics, infrastructure, and software test environments.

The goal is:
- reliability
- maintainability
- observability
- testability
- simplicity

Do NOT overengineer solutions.

Prefer:
- clear code
- modular design
- readable functions
- strong logging
- practical abstractions
- straightforward debugging

Avoid:
- unnecessary frameworks
- excessive abstraction
- premature optimization
- complex design patterns unless justified

---

# Engineering Standards

## Code Quality

- Follow PEP8
- Use type hints where practical
- Write docstrings for public functions
- Keep functions focused and small
- Prefer explicit behavior over "magic"

When generating code:
- explain important architectural decisions
- explain tradeoffs
- explain why a design is appropriate

Do not silently introduce major dependencies.

---

# Testing Requirements

Testing is mandatory.

Whenever adding functionality:
- create or update pytest tests
- validate edge cases
- validate failure handling
- avoid brittle tests

Prefer:
- deterministic tests
- isolated unit tests
- meaningful assertions

Mock external systems appropriately.

---

# Logging and Debugging

This project should be easy to debug in production-like environments.

Use:
- structured logging where appropriate
- clear error messages
- actionable debugging output

Avoid:
- excessive console spam
- swallowing exceptions silently

---

# Project Structure

Prefer clean and conventional Python project layouts.

Use:
- pyproject.toml
- src/ layout
- tests/ directory
- clear module separation

Keep the structure understandable for recruiters and collaborators.

---

# Dependencies

Minimize dependencies.

Before adding a package:
- explain why it is needed
- prefer standard library solutions when reasonable

Avoid dependency bloat.

---

# Documentation

Maintain:
- clean README
- setup instructions
- usage examples
- architecture overview
- testing instructions

Assume the audience is:
- robotics engineers
- software infrastructure engineers
- hiring managers
- recruiters

README files should sound professional and concise.

---

# Git and Commits

Prefer small logical commits.

Suggested commit style:
- feat:
- fix:
- refactor:
- test:
- docs:

Example:
feat: add parallel robot health check runner

---

# Security and Privacy

Do not include:
- proprietary company information
- internal APIs
- confidential workflows
- real credentials
- real production endpoints

Use mock systems and simulated environments only.

---

# AI Collaboration Rules

When making major decisions:
- explain reasoning first
- explain alternatives considered
- mention tradeoffs

Do not blindly generate large amounts of code without explanation.

Prefer iterative development:
1. plan
2. implement
3. test
4. review
5. refine

If requirements are unclear:
- ask clarifying questions
- do not invent functionality

---

# Preferred Technologies

Preferred stack:
- Python
- pytest
- argparse or typer
- YAML configuration
- GitHub Actions
- Docker (when useful)

Avoid unnecessary frontend complexity unless explicitly requested.

---

# Portfolio Focus

This repository is intended to strengthen:
- robotics software engineering applications
- infrastructure engineering applications
- software test engineering applications
- DevOps/SRE style workflows

Code should demonstrate:
- debugging ability
- reliability engineering
- automation
- release validation thinking
- operational awareness

---

# Important Constraint

Keep the first implementation simple and working.

A smaller polished project is preferred over a large unfinished system.
