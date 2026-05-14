from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Robot:
    name: str
    host: str
    type: str
    tags: list[str] = field(default_factory=list)
    port: int = 22
    user: str = "robot"


@dataclass
class FleetConfig:
    robots: list[Robot]

    def get_robot(self, name: str) -> Robot | None:
        return next((r for r in self.robots if r.name == name), None)

    def filter_by_tag(self, tag: str) -> list[Robot]:
        return [r for r in self.robots if tag in r.tags]


def load_config(path: str | Path) -> FleetConfig:
    """Load fleet configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    robots = [Robot(**entry) for entry in data.get("robots", [])]
    logger.info("Loaded %d robot(s) from %s", len(robots), path)
    return FleetConfig(robots=robots)
