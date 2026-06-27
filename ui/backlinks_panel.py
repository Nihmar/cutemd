"""Backlinks panel — shows files that link to the current note.

Scans all .md files in the vault for wikilinks and markdown links
pointing to the currently open file.  Runs in a background QThread.
Uses the same link-detection and resolution logic as the editor.
"""

import re
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QLabel, QListWidgetItem, QVBoxLayout, QWidget

from core.link_resolution import resolve_link_target
from core.logging import setup_logging
from ui.widgets import CuteListWidget

_LOG = setup_logging("cutemd.backlinks")

# ---------------------------------------------------------------------------
# Regex patterns — identical to the ones in ui/link_manager.py
# ---------------------------------------------------------------------------
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")


def _extract_wikilink_targets(inner: str) -> list[str]:
    """Extract candidate file targets from a wikilink's inner text.

    Handles ``[[target]]``, ``[[target|alias]]``, ``[[target#heading]]``,
    and combinations.  Checks both sides of ``|`` since the editor's
    ``link_range_at`` resolves using the part *after* the pipe.
    """
    targets: list[str] = []
    # Split on pipe
    parts = inner.split("|")
    for part in parts:
        # Strip heading anchors (but keep targets that start with # —
        # those are same-file heading links, not backlinks to other files)
        if part.startswith("#"):
            continue
        file_part = part.split("#")[0].strip()
        if file_part:
            targets.append(file_part)
    return targets


class BacklinkScanner(QThread):
    """Background worker that walks .md files and finds backlinks."""

    backlink_found = Signal(str)  # absolute file path
    scan_complete = Signal()

    def __init__(
        self,
        folder_path: Path,
        current_file: Path,
        attachments_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._folder_path = folder_path
        self._current_file = current_file.resolve()
        self._attachments_dir = attachments_dir

    def run(self) -> None:
        _LOG.debug("BacklinkScanner: scanning in %s for %s",
                   self._folder_path, self._current_file.name)
        try:
            for md_file in sorted(self._folder_path.rglob("*.md")):
                if self.isInterruptionRequested():
                    _LOG.debug("BacklinkScanner: interrupted")
                    return

                try:
                    if md_file.resolve() == self._current_file:
                        continue
                except OSError:
                    continue

                try:
                    text = md_file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                if self._has_backlink(text, md_file.parent):
                    _LOG.debug("BacklinkScanner: found %s \u2192 %s",
                               md_file.name, self._current_file.name)
                    self.backlink_found.emit(str(md_file))

            # Also walk .markdown files
            for md_file in sorted(self._folder_path.rglob("*.markdown")):
                if self.isInterruptionRequested():
                    return
                try:
                    if md_file.resolve() == self._current_file:
                        continue
                except OSError:
                    continue
                try:
                    text = md_file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if self._has_backlink(text, md_file.parent):
                    self.backlink_found.emit(str(md_file))

        except Exception:
            _LOG.exception("BacklinkScanner: error during scan")

        _LOG.debug("BacklinkScanner: scan complete")
        self.scan_complete.emit()

    def _has_backlink(self, text: str, source_dir: Path) -> bool:
        """Check if *text* contains a link whose resolved target matches the
        current file.
        """
        # Wikilinks
        for m in _WIKILINK_RE.finditer(text):
            inner = m.group(1).strip()
            targets = _extract_wikilink_targets(inner)
            for target in targets:
                if self._target_matches(target, source_dir):
                    _LOG.debug("_has_backlink WIKI match: target=%r source=%s",
                               target, source_dir)
                    return True

        # Markdown links
        for m in _LINK_RE.finditer(text):
            url = m.group(2).strip()
            # Skip external URLs and same-file heading refs
            if url.startswith(("http://", "https://", "mailto:", "#", "www.")):
                continue
            if self._target_matches(url, source_dir):
                _LOG.debug("_has_backlink MD match: url=%r source=%s",
                           url, source_dir)
                return True

        return False

    def _target_matches(self, target: str, source_dir: Path) -> bool:
        """Check if *target* (from a file in *source_dir*) could refer to the
        current file.

        Uses the same logic as clicking a link in the editor: attempts to
        resolve via ``resolve_link_target`` first (quick mode), then falls
        back to stem-based matching for link targets that include paths or
        URL-encoding.
        """
        # First try: resolve via resolve_link_target (quick mode)
        resolved = resolve_link_target(
            target, source_dir, self._attachments_dir, quick=True,
        )
        if resolved is not None and resolved.resolve() == self._current_file:
            _LOG.debug("_target_matches: resolve match target=%r", target)
            return True

        # Fallback: stem-based name matching
        # Handles cases where resolve_link_target misses due to vault_root issues
        try:
            decoded = unquote(target)
        except Exception:
            decoded = target
        target_path = Path(decoded)
        target_stem = target_path.stem
        if target_stem.lower() == self._current_file.stem.lower():
            _LOG.debug("_target_matches: stem match target=%r stem=%r",
                       target, target_stem)
            return True
        return False


class BacklinksPanel(QWidget):
    """Sidebar panel listing files that contain links to the current note.

    Emits:
        backlink_activated(str) — absolute path of the clicked file.
    """

    backlink_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._status_label = QLabel(self.tr("No backlinks"))
        self._status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        layout.addWidget(self._status_label)

        self._list = CuteListWidget()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        self._scan_thread: BacklinkScanner | None = None
        self._entries: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_scan(
        self,
        folder_path: Path,
        current_file: Path,
        attachments_dir: Path | None = None,
    ) -> None:
        """Cancel any running scan and start a new one."""
        _LOG.debug("start_scan: file=%s", current_file.name)
        self._cancel_scan()

        self._list.clear()
        self._entries.clear()
        self._status_label.setText(self.tr("Scanning\u2026"))
        self._status_label.show()

        self._scan_thread = BacklinkScanner(
            folder_path, current_file, attachments_dir, self,
        )
        self._scan_thread.backlink_found.connect(self._on_backlink_found)
        self._scan_thread.scan_complete.connect(self._on_scan_complete)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def clear(self) -> None:
        """Cancel any scan and clear the panel."""
        _LOG.debug("clear")
        self._cancel_scan()
        self._list.clear()
        self._entries.clear()
        self._status_label.setText(self.tr("No backlinks"))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cancel_scan(self) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            _LOG.debug("_cancel_scan: interrupting running scan")
            self._scan_thread.requestInterruption()
            self._scan_thread.wait(2000)

    def _on_backlink_found(self, filepath: str) -> None:
        _LOG.debug("_on_backlink_found: %s", filepath)
        p = Path(filepath)
        item = QListWidgetItem(p.name)
        item.setData(Qt.ItemDataRole.UserRole, filepath)
        item.setToolTip(filepath)
        self._list.addItem(item)
        self._entries.append(filepath)

    def _on_scan_complete(self) -> None:
        count = len(self._entries)
        if count == 0:
            self._status_label.setText(self.tr("No backlinks"))
        elif count == 1:
            self._status_label.setText(self.tr("1 backlink"))
        else:
            self._status_label.setText(self.tr("{} backlinks").format(count))
        _LOG.debug("_on_scan_complete: %d backlinks", count)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if filepath:
            self.backlink_activated.emit(filepath)
