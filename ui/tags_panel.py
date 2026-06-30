"""Tags panel — collects tags from YAML frontmatter and inline #tags.

Scans all .md files in the vault on folder open and on save.
Runs in a background QThread.  Displays tags in a QTreeWidget with
note filenames as children.
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.logging import setup_logging
from core.vault_scanner import VaultScanner

_LOG = setup_logging("cutemd.tags")
from core.frontmatter import parse_frontmatter, _FRONTMATTER_RE

# Inline tag detection: #tag  (not at line start to avoid matching headings)
_INLINE_TAG_RE = re.compile(r"(?<=\s)#([\w\u0080-\uFFFF][\w\u0080-\uFFFF-]*)")
_START_TAG_RE = re.compile(r"(?<!\S)#([\w\u0080-\uFFFF][\w\u0080-\uFFFF-]*)")


def _parse_yaml_tags(text: str) -> list[str]:
    """Extract tags from YAML frontmatter ``tags:`` field."""
    fm = parse_frontmatter(text)
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        return []
    result: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            t = str(t)
        t = t.strip().strip("\"'").lstrip("#")
        if t:
            result.append(t)
    return result


def _collect_inline_tags(text: str) -> list[str]:
    """Find inline ``#tag`` tokens in the note body (excluding frontmatter)."""
    body = _FRONTMATTER_RE.sub("", text, count=1)
    tags: set[str] = set()
    for m in _INLINE_TAG_RE.finditer(body):
        tags.add(m.group(1))
    return sorted(tags)


class TagScanner(QThread):
    """Background worker that collects all tags from .md files in a vault."""

    tag_found = Signal(str, str)  # tag, filepath
    scan_complete = Signal()

    def __init__(
        self,
        folder_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._folder_path = folder_path

    def run(self) -> None:
        _LOG.debug("TagScanner: scanning %s", self._folder_path)
        try:
            # Single walk for both .md and .markdown files.
            md_files = sorted(
                p for p in self._folder_path.rglob("*")
                if p.is_file() and p.suffix.lower() in (".md", ".markdown")
                    and ".trash" not in p.parts
                    and ".cutemd" not in p.parts
            )
            for md_file in md_files:
                if self.isInterruptionRequested():
                    _LOG.debug("TagScanner: interrupted")
                    return
                try:
                    text = md_file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                tags: set[str] = set()

                # YAML frontmatter tags
                for t in _parse_yaml_tags(text):
                    tags.add(t)

                # Inline #tags
                for t in _collect_inline_tags(text):
                    tags.add(t)

                for tag in sorted(tags):
                    self.tag_found.emit(tag, str(md_file))

        except Exception:
            _LOG.exception("TagScanner: error during scan")

        _LOG.debug("TagScanner: scan complete")
        self.scan_complete.emit()


class TagsPanel(QWidget):
    """Sidebar panel displaying all tags in the vault as a tree.

    Top-level items are tag names; children are note filenames.
    Clicking a note opens it in a new tab.

    Emits:
        tag_note_activated(str) — absolute path of the clicked note.
        tags_updated(list) — list of unique tag names after scan completes.
    """

    tag_note_activated = Signal(str)
    tags_updated = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._status_label = QLabel(self.tr("No tags"))
        self._status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        layout.addWidget(self._status_label)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText(self.tr("Filter tags…"))
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter_edit)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

        self._scan_thread: TagScanner | None = None
        self._tag_items: dict[str, QTreeWidgetItem] = {}
        self._tag_counts: dict[str, int] = {}
        # Batch processing — avoids flooding the event loop with tree
        # item creation during bulk tag loads.
        self._tag_buffer: list[tuple[str, list[str]]] = []
        self._tag_batch_timer = QTimer(self)
        self._tag_batch_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tag_batch_timer.setInterval(5)
        self._tag_batch_timer.timeout.connect(self._flush_tag_batch)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_scan(self, scanner: VaultScanner) -> None:
        """Connect to *scanner* and rebuild tags from its output.
        Tags are extracted in the scanner's worker thread — only the
        result list is sent via signal, not the full file content."""
        _LOG.debug("start_scan: connecting to VaultScanner")
        self._tag_batch_timer.stop()
        self._tag_buffer.clear()
        self._tree.clear()
        self._tag_items.clear()
        self._tag_counts.clear()
        self._status_label.setText(self.tr("Scanning\u2026"))
        self._status_label.show()

        self._scanner = scanner
        scanner.file_tags.connect(self._on_file_tags)
        scanner.scan_complete.connect(self._on_scan_complete)

    def clear(self) -> None:
        """Cancel any scan and clear the panel."""
        _LOG.debug("clear")
        self._tag_batch_timer.stop()
        self._tag_buffer.clear()
        self._cancel_scan()
        self._tree.clear()
        self._tag_items.clear()
        self._tag_counts.clear()
        self._filter_edit.clear()
        self._status_label.setText(self.tr("No tags"))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        """Show/hide tree items based on filter text."""
        low = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if not low or low in item.text(0).lower():
                item.setHidden(False)
                if low:
                    item.setExpanded(True)
                else:
                    item.setExpanded(False)
            else:
                # Check children too
                child_match = False
                for j in range(item.childCount()):
                    child = item.child(j)
                    if low in child.text(0).lower():
                        child_match = True
                        break
                if child_match:
                    item.setHidden(False)
                    item.setExpanded(True)
                else:
                    item.setHidden(True)

    def _cancel_scan(self) -> None:
        """Disconnect from any active scanner."""
        if hasattr(self, '_scanner') and self._scanner is not None:
            try:
                self._scanner.file_tags.disconnect(self._on_file_tags)
                self._scanner.scan_complete.disconnect(self._on_scan_complete)
            except (RuntimeError, TypeError):
                pass
            self._scanner = None

    def _on_file_tags(self, filepath: Path, tags: list[str]) -> None:
        """Buffer tags from the scanner — actual tree population is
        deferred to ``_flush_tag_batch`` which runs via a 5ms timer,
        allowing paint events to interleave."""
        self._tag_buffer.append((str(filepath), tags))
        if not self._tag_batch_timer.isActive():
            self._tag_batch_timer.start()

    def _flush_tag_batch(self) -> None:
        """Process one batch of buffered tags into the tree widget.
        Processes up to 20 items per tick so the event loop has time
        to paint between batches."""
        batch = min(20, len(self._tag_buffer))
        for _ in range(batch):
            if not self._tag_buffer:
                break
            fp_str, tags = self._tag_buffer.pop(0)
            for tag in tags:
                if tag not in self._tag_items:
                    item = QTreeWidgetItem(self._tree, [tag])
                    item.setData(0, Qt.ItemDataRole.UserRole, "")
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    self._tag_items[tag] = item
                    self._tag_counts[tag] = 0
                self._tag_counts[tag] = self._tag_counts.get(tag, 0) + 1
                child = QTreeWidgetItem(self._tag_items[tag])
                child.setText(0, fp_str)
                child.setData(0, Qt.ItemDataRole.UserRole, fp_str)
                child.setToolTip(0, fp_str)
        if not self._tag_buffer:
            self._tag_batch_timer.stop()

    def _on_scan_complete(self) -> None:
        """Flush remaining buffered tags and stop the batch timer."""
        self._tag_batch_timer.stop()
        while self._tag_buffer:
            self._flush_tag_batch()
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
        total_tags = len(self._tag_items)
        total_files = sum(self._tag_counts.values())
        if total_tags == 0:
            self._status_label.setText(self.tr("No tags"))
        else:
            self._status_label.setText(
                self.tr("{} tags in {} notes").format(total_tags, total_files)
            )
        _LOG.debug("_on_scan_complete: %d tags, %d notes",
                   total_tags, total_files)
        # Emit tag names so the editor completer can pick them up
        self.tags_updated.emit(sorted(self._tag_items.keys()))

    def _on_scan_finished(self) -> None:
        """Clean up the finished thread reference."""
        self._scan_thread = None

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        if filepath:
            self.tag_note_activated.emit(filepath)
