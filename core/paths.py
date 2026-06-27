"""Centralized path resolution — PyInstaller-aware.

Every module that needs to locate bundled data files should import
from here instead of duplicating the ``getattr(sys, 'frozen', False)``
pattern.
"""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_path(*segments: str) -> Path:
    """Resolve a path relative to the application root, supporting PyInstaller.

    When running from a PyInstaller bundle, resolves relative to the
    temporary extraction directory (``sys._MEIPASS``).  When running
    from source, resolves relative to the project root (two levels up
    from this module, i.e. ``cutemd/core/`` → ``cutemd/``).

    Usage::

        css_path = resolve_path("ui", "preview_styles.css")
    """
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        root = Path(__file__).resolve().parent.parent
    return root.joinpath(*segments)


def resolve_icon_path() -> Path:
    """Return the absolute path to the application icon (SVG)."""
    return resolve_path("resources", "cutemd.svg")
