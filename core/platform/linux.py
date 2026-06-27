"""Desktop integration utilities for AppImage — install .desktop + icon."""

import os
import shutil
import subprocess
from pathlib import Path

from core.paths import resolve_path

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
    icon_src = resolve_path("resources", "cutemd.svg")
    if icon_src.is_file():
        shutil.copy2(str(icon_src), str(icon_dir / "cutemd.svg"))

    # Refresh desktop database
    subprocess.run(
        ["update-desktop-database", str(desktop_dir)],
        capture_output=True,
    )

    return str(desktop_path)
