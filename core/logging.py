"""Shared logging infrastructure for CuteMD.

Provides a single ``setup_logging`` function that returns a configured logger.
Logs are written to stderr when the application is launched from a terminal
(``uv run main.py``). When launched via GUI (double-click, .exe, AppImage),
a ``NullHandler`` is used and all output is silently discarded.

No log files are created on disk.
"""

from __future__ import annotations

import logging
import sys


def _detect_terminal() -> bool:
    if sys.stderr.isatty():
        return True
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        try:
            import ctypes
            return ctypes.windll.kernel32.GetConsoleWindow() != 0
        except Exception:
            pass
    return False


_IS_TERMINAL = _detect_terminal()


def setup_logging(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Create a logger that outputs to stderr only in terminal mode.

    Args:
        name: Logger name, e.g. ``"cutemd.main_window"``.
        level: Log level (default ``DEBUG``).

    Returns:
        A configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if _IS_TERMINAL:
        try:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(level)
            handler.setFormatter(
                logging.Formatter("%(name)s %(levelname)s %(message)s")
            )
            logger.addHandler(handler)
        except Exception:
            logger.addHandler(logging.NullHandler())
    else:
        logger.addHandler(logging.NullHandler())

    return logger
