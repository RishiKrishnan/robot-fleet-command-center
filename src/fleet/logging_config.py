import logging
import sys


def setup_logging(level: str = "WARNING") -> None:
    """Configure application-wide logging to stderr."""
    numeric_level = getattr(logging, level.upper(), logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logging.basicConfig(level=numeric_level, handlers=[handler], force=True)
