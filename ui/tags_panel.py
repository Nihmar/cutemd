"""Tags panel — collects tags from YAML frontmatter and inline #tags.

Scans all .md files in the vault on folder open and on save.
Runs in a background QThread.  Displays tags in a QTreeWidget with
note filenames as children.
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.logging import setup_logging

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
            for md_file in sorted(self._folder_path.rglob("*.md")):
                if self.isInterruptionRequested():
                    _LOG.debug("TagScanner: interrupted")
                    return
                # Skip trashed and history files
                if ".trash" in md_file.parts or ".cutemd" in md_file.parts:
                    continue
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

            # Also scan .markdown files
            for md_file in sorted(self._folder_path.rglob("*.markdown")):
                if self.isInterruptionRequested():
                    return
                try:
                    text = md_file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                tags: set[str] = set()
                for t in _parse_yaml_tags(text):
                    tags.add(t)
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_scan(self, folder_path: Path) -> None:
        """Cancel any running scan and start a new one."""
        _LOG.debug("start_scan: %s", folder_path)
        self._cancel_scan()

        self._tree.clear()
        self._tag_items.clear()
        self._tag_counts.clear()
        self._status_label.setText(self.tr("Scanning\u2026"))
        self._status_label.show()

        self._scan_thread = TagScanner(folder_path, self)
        self._scan_thread.tag_found.connect(self._on_tag_found)
        self._scan_thread.scan_complete.connect(self._on_scan_complete)
        self._scan_thread.finished.connect(self._on_scan_finished)
        self._scan_thread.start()

    def clear(self) -> None:
        """Cancel any scan and clear the panel."""
        _LOG.debug("clear")
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
        if self._scan_thread is not None:
            try:
                if self._scan_thread.isRunning():
                    _LOG.debug("_cancel_scan: interrupting running scan")
                    self._scan_thread.requestInterruption()
                    self._scan_thread.wait(2000)
            except RuntimeError:
                pass  # C++ object already deleted
        self._scan_thread = None

    def _on_tag_found(self, tag: str, filepath: str) -> None:
        _LOG.debug("_on_tag_found: %s → %s", tag, Path(filepath).name)
        if tag not in self._tag_items:
            item = QTreeWidgetItem(self._tree, [tag])
            item.setData(0, Qt.ItemDataRole.UserRole, "")  # tag node, not clickable
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            # Collapsed by default (will expand on click or filter)
            self._tag_items[tag] = item
            self._tag_counts[tag] = 0

        parent = self._tag_items[tag]
        child = QTreeWidgetItem(parent, [Path(filepath).name])
        child.setData(0, Qt.ItemDataRole.UserRole, filepath)
        child.setToolTip(0, filepath)
        self._tag_counts[tag] += 1

    def _on_scan_complete(self) -> None:
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
        self._scan_thread = None
        # Emit tag names so the editor completer can pick them up
        self.tags_updated.emit(sorted(self._tag_items.keys()))

    def _on_scan_finished(self) -> None:
        """Clean up the finished thread reference."""
        self._scan_thread = None

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        if filepath:
            self.tag_note_activated.emit(filepath)
