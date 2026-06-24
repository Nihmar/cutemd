"""Read KDE / GNOME animation speed preferences."""

from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


def animation_duration_ms(base_ms: int = 150) -> int:
    """Return *base_ms* scaled by the system animation speed factor.

    Reads ``AnimationDurationFactor`` from ``~/.config/kdeglobals``
    (KDE Plasma) and ``enable-animations`` from the GNOME gsettings
    path.  Falls back to *base_ms* if nothing is detected.
    """
    factor = _detect_factor()
    return max(0, int(base_ms * factor))


def _detect_factor() -> float:
    # KDE Plasma — kdeglobals
    kde_config = _read_kdeglobals()
    if kde_config is not None:
        try:
            factor = float(kde_config["KDE"]["AnimationDurationFactor"])
            return max(0.0, min(factor, 3.0))
        except (KeyError, ValueError):
            pass

    # GNOME — check if animations are disabled entirely
    if not _gnome_animations_enabled():
        return 0.0

    return 1.0


def _read_kdeglobals() -> ConfigParser | None:
    path = Path.home() / ".config" / "kdeglobals"
    if not path.is_file():
        return None
    cp = ConfigParser()
    try:
        cp.read_string(path.read_text())
    except Exception:
        return None
    return cp if "KDE" in cp else None


def _gnome_animations_enabled() -> bool:
    import subprocess

    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return "true" in result.stdout.lower()
    except Exception:
        return True  # assume enabled if we can't check
