"""Desktop integration utilities for AppImage — install .desktop + icon."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

_DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=CuteMD
Comment=A non-WYSIWYG Markdown editor
Exec={appimage} %F
Icon=cutemd
Terminal=false
Categories=Office;TextEditor;
MimeType=text/markdown;text/x-markdown;
StartupNotify=true
"""


def _appimage_path() -> str | None:
    """Return the AppImage file path if running from one, else None."""
    return os.environ.get("APPIMAGE")


def _resolve_path_in_bundle(name: str) -> Path | None:
    """Resolve a data file bundled by PyInstaller."""
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        root = Path(__file__).resolve().parent.parent
    candidate = root / name
    return candidate if candidate.is_file() else None


def is_desktop_installed() -> bool:
    desktop = Path.home() / ".local" / "share" / "applications" / "cutemd.desktop"
    return desktop.is_file()


def install_desktop() -> str:
    """Install .desktop file and icon to ~/.local. Returns success message
    or raises OSError."""
    appimage = _appimage_path()
    if not appimage:
        raise OSError("Not running from an AppImage (APPIMAGE env var not set).")

    desktop_dir = Path.home() / ".local" / "share" / "applications"
    icon_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"

    desktop_dir.mkdir(parents=True, exist_ok=True)
    icon_dir.mkdir(parents=True, exist_ok=True)

    # Write .desktop with the actual AppImage path
    desktop_content = _DESKTOP_TEMPLATE.format(appimage=appimage)
    desktop_path = desktop_dir / "cutemd.desktop"
    desktop_path.write_text(desktop_content, encoding="utf-8")

    # Copy icon from bundle
    icon_src = _resolve_path_in_bundle("resources/cutemd.svg")
    if icon_src:
        shutil.copy2(str(icon_src), str(icon_dir / "cutemd.svg"))

    # Refresh desktop database
    subprocess.run(
        ["update-desktop-database", str(desktop_dir)],
        capture_output=True,
    )

    return str(desktop_path)
