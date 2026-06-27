"""File I/O and folder utilities — pure logic, no Qt imports."""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# File reading with encoding detection
# ---------------------------------------------------------------------------


def read_file_with_encoding(path: Path) -> tuple[str | None, str]:
    """Read a file trying multiple encodings. Returns (text, encoding) or
    (None, error_message)."""
    try:
        return path.read_text(encoding="utf-8"), "utf-8"
    except (UnicodeDecodeError, UnicodeError):
        pass
    for enc in ("utf-8-sig", "cp1252", "iso-8859-1", "latin-1", "ascii"):
        try:
            return path.read_text(encoding=enc), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    try:
        raw = path.read_bytes()
        return raw.decode("utf-8", errors="replace"), "utf-8 (broken)"
    except OSError as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Per-folder initialisation
# ---------------------------------------------------------------------------


def default_folder_config(
    global_theme: str,
    editor_font_family: str,
    editor_font_size: int,
    preview_font_family: str,
    preview_font_size: int,
    attachments_dir: str = "images",
) -> dict[str, object]:
    """Return the default per-folder settings dict, seeded from global values."""
    return {
        "theme": global_theme,
        "editor_font_family": editor_font_family,
        "editor_font_size": editor_font_size,
        "preview_font_family": preview_font_family,
        "preview_font_size": preview_font_size,
        "attachments_dir": attachments_dir,
    }


# ---------------------------------------------------------------------------
# Recent folders
# ---------------------------------------------------------------------------


def update_recent_folders(
    current: list[str], new_path: str, max_items: int = 10
) -> list[str]:
    """Add *new_path* to the front of the list, removing duplicates."""
    result = [p for p in current if p != new_path]
    result.insert(0, new_path)
    return result[:max_items]
