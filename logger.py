"""Centralized logging for job_hunt_tool."""

import logging
import logging.handlers
import os
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the job_hunt hierarchy."""
    return logging.getLogger(f"job_hunt.{name}")


def setup_logging(level: str = None) -> None:
    """Configure root job_hunt logger with console + rotating file handlers."""
    log_level = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)

    root = logging.getLogger("job_hunt")
    if root.handlers:
        return  # already configured

    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — respects LOG_LEVEL
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler — always DEBUG
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "job_hunt.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)


setup_logging()
