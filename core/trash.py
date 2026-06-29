"""Trash bin — moves deleted files to .trash/ instead of permanent deletion."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def trash_path(vault_root: Path) -> Path:
    return vault_root / ".trash"


def trash_file(file_path: Path, vault_root: Path) -> Path | None:
    """Move *file_path* into .trash/ preserving relative structure.

    Returns the path inside .trash/, or None on failure.
    """
    trash = trash_path(vault_root)
    try:
        rel = file_path.resolve().relative_to(vault_root.resolve())
    except ValueError:
        return None

    dest = trash / rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Avoid overwriting: append timestamp
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = dest.parent / f"{dest.stem}_{ts}{dest.suffix}"

    try:
        shutil.move(str(file_path), str(dest))
        return dest
    except OSError:
        return None


def restore_file(trashed: Path, vault_root: Path) -> Path | None:
    """Move *trashed* back to its original location."""
    try:
        rel = trashed.resolve().relative_to(trash_path(vault_root).resolve())
    except ValueError:
        return None

    dest = vault_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(trashed), str(dest))
        return dest
    except OSError:
        return None


def permanent_delete(trashed: Path) -> bool:
    """Remove a trashed file permanently."""
    try:
        if trashed.is_file():
            trashed.unlink()
        elif trashed.is_dir():
            shutil.rmtree(trashed)
        return True
    except OSError:
        return False


def list_trash(vault_root: Path) -> list[Path]:
    """List all trashed files."""
    trash = trash_path(vault_root)
    if not trash.is_dir():
        return []
    return sorted(
        p for p in trash.rglob("*") if p.is_file() and not p.name.startswith(".")
    )
