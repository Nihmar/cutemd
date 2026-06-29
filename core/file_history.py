"""File history — stores snapshots of files on every save."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def history_dir(vault_root: Path, file_path: Path) -> Path:
    try:
        rel = file_path.resolve().relative_to(vault_root.resolve())
    except ValueError:
        return vault_root / ".cutemd" / "history" / file_path.name
    return vault_root / ".cutemd" / "history" / rel


def save_snapshot(file_path: Path, vault_root: Path) -> Path | None:
    """Copy *file_path* to .cutemd/history/<rel>/<timestamp>.md"""
    hdir = history_dir(vault_root, file_path)
    hdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:17]  # YYYYMMDD_HHMMSS_ms
    dest = hdir / f"{ts}.md"
    try:
        shutil.copy2(str(file_path), str(dest))
        return dest
    except OSError:
        return None


def list_snapshots(vault_root: Path, file_path: Path) -> list[Path]:
    """List all saved snapshots for *file_path*, newest first."""
    hdir = history_dir(vault_root, file_path)
    if not hdir.is_dir():
        return []
    return sorted(hdir.glob("*.md"), reverse=True)


def cleanup_snapshots(vault_root: Path, file_path: Path, max_count: int) -> None:
    """Keep only the most recent *max_count* snapshots."""
    snapshots = list_snapshots(vault_root, file_path)
    if len(snapshots) <= max_count:
        return
    for old in snapshots[max_count:]:
        try:
            old.unlink()
        except OSError:
            pass


def restore_snapshot(snapshot: Path, target: Path) -> bool:
    """Copy *snapshot* back to *target*."""
    try:
        shutil.copy2(str(snapshot), str(target))
        return True
    except OSError:
        return False
