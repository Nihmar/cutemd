"""File reading with encoding detection — pure logic, no Qt imports."""

from __future__ import annotations

from pathlib import Path


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
