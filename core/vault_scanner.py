"""Single-pass vault scanner — one rglob, feeds tags + backlinks + file list.

Replaces the independent TagScanner, BacklinkScanner, and
_collect_vault_files() rglob calls with a unified background thread
that walks the vault once and emits file paths + contents to all
interested consumers.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.vault_scanner")

_MD_SUFFIXES = (".md", ".markdown")


class VaultScanner(QThread):
    """Background worker that walks a vault folder and emits every
    Markdown file (path + text content) exactly once per scan.

    Consumers connect to ``file_found`` (for file-list UIs) and
    ``file_content`` (for tag / backlink extraction).  On subsequent
    scans only files whose ``mtime`` changed are re-emitted.
    """

    file_found = Signal(Path)        # emitted for every Markdown file
    file_content = Signal(Path, str)  # path + UTF-8 text content
    scan_complete = Signal()

    def __init__(self, folder_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder_path
        self._mtime_cache: dict[Path, float] = {}

    def run(self) -> None:
        _LOG.debug("VaultScanner: scanning %s", self._folder)
        try:
            for p in self._folder.rglob("*"):
                if self.isInterruptionRequested():
                    _LOG.debug("VaultScanner: interrupted")
                    return
                if not p.is_file():
                    continue
                if p.suffix.lower() not in _MD_SUFFIXES:
                    continue
                if ".trash" in p.parts or ".cutemd" in p.parts:
                    continue

                self.file_found.emit(p)

                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue

                cached = self._mtime_cache.get(p)
                if cached is not None and cached == mtime:
                    continue  # unchanged — skip content read

                self._mtime_cache[p] = mtime

                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                self.file_content.emit(p, text)
        except Exception:
            _LOG.exception("VaultScanner: error during scan")

        _LOG.debug("VaultScanner: scan complete")
        self.scan_complete.emit()

    def invalidate(self) -> None:
        """Clear the mtime cache — next scan re-emits all files."""
        self._mtime_cache.clear()
