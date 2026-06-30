"""Single-pass vault scanner — one rglob, feeds tags + backlinks + file list.

Replaces the independent TagScanner, BacklinkScanner, and
_collect_vault_files() rglob calls with a unified background thread
that walks the vault once and emits file paths + contents to all
interested consumers.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.logging import setup_logging
from core.search_index import SearchIndex
from core.frontmatter import parse_frontmatter, _FRONTMATTER_RE

_LOG = setup_logging("cutemd.vault_scanner")

_MD_SUFFIXES = (".md", ".markdown")

_INLINE_TAG_RE = re.compile(r"(?<=\s)#([\w\u0080-\uFFFF][\w\u0080-\uFFFF-]*)")

def _extract_tags(text: str) -> list[str]:
    """Extract tags from YAML frontmatter and inline #tags."""
    fm = parse_frontmatter(text)
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        tags = []
    result: set[str] = set()
    for t in tags:
        if not isinstance(t, str):
            t = str(t)
        t = t.strip().strip("\"'").lstrip("#")
        if t:
            result.add(t)
    body = _FRONTMATTER_RE.sub("", text, count=1)
    for m in _INLINE_TAG_RE.finditer(body):
        result.add(m.group(1))
    return list(result)


class VaultScanner(QThread):
    """Background worker that walks a vault folder and emits every
    Markdown file (path + text content) exactly once per scan.

    Consumers connect to ``file_found`` (for file-list UIs) and
    ``file_content`` (for tag / backlink extraction).  On subsequent
    scans only files whose ``mtime`` changed are re-emitted.

    If ``search_index`` is provided, every indexed file is added to
    the inverted word→file index during the scan.
    """

    file_found = Signal(Path)        # emitted for every Markdown file
    file_content = Signal(Path, str)  # path + UTF-8 text content
    file_tags = Signal(Path, list)    # path + list of extracted tag strings
    scan_complete = Signal()

    def __init__(self, folder_path: Path, search_index: SearchIndex | None = None, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder_path
        self._mtime_cache: dict[Path, float] = {}
        self._search_index = search_index

    def run(self) -> None:
        _LOG.debug("VaultScanner: scanning %s", self._folder)
        try:
            for i, p in enumerate(self._folder.rglob("*")):
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

                # Throttle signal emission — prevents flooding the event
                # queue on Windows where file-system operations are slower.
                if i % 20 == 0:
                    self.msleep(1)

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

                if self._search_index is not None:
                    self._search_index.add_file(p, text)

                # Extract tags in the worker thread — avoids sending
                # large text payloads through the Qt event queue.
                tags = _extract_tags(text)
                if tags:
                    self.file_tags.emit(p, tags)

                self.file_content.emit(p, text)
        except Exception:
            _LOG.exception("VaultScanner: error during scan")

        _LOG.debug("VaultScanner: scan complete")
        self.scan_complete.emit()

    def invalidate(self) -> None:
        """Clear the mtime cache — next scan re-emits all files."""
        self._mtime_cache.clear()
