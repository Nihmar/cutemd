"""Shared logging infrastructure for CuteMD.

Provides a single ``setup_logging`` function that returns a configured logger.
All output goes to ``sys.stderr``. Visibility depends on how the app is launched:

- **Terminal** (``uv run main.py``): stderr is your terminal — log lines appear live
- **GUI** (double-click ``.exe`` / AppImage): stderr goes nowhere — no clutter
- **No log files** are ever created on disk
"""

from __future__ import annotations

import logging
import sys


def setup_logging(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Create a logger that writes to stderr.

    Args:
        name: Logger name, e.g. ``"cutemd.main_window"``.
        level:  Log level (default ``DEBUG``).

    Returns:
        A configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(name)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    return logger
