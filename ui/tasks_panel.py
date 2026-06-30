"""Tasks panel — scans .md files for todo items and shows them grouped
by done / not-done using configurable keywords.

Keywords (e.g. ``#task_todo`` / ``#task_done``) are read from QSettings
at scan time so changes take effect on the next scan.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QLabel, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from core.logging import setup_logging

_LOG = setup_logging("cutemd.tasks")

_TASK_RE = re.compile(r"^- \[([ x])\] (.+)$", re.MULTILINE)
_DEFAULT_TASK_KEYWORD = "#task_todo"


class _TaskScanner(QThread):
    """Background worker that walks .md files and emits task items."""

    task_found = Signal(Path, int, str, bool)  # file, line_number, text, is_done
    scan_complete = Signal()

    def __init__(
        self,
        folder_path: Path,
        task_keyword: str = _DEFAULT_TASK_KEYWORD,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._folder = folder_path
        self._task_kw = task_keyword.lower()
        self._mtime_cache: dict[Path, float] = {}

    def run(self) -> None:
        _LOG.debug("TaskScanner: scanning %s", self._folder)
        try:
            for p in self._folder.rglob("*"):
                if self.isInterruptionRequested():
                    _LOG.debug("TaskScanner: interrupted")
                    return
                if not p.is_file():
                    continue
                if p.suffix.lower() not in (".md", ".markdown"):
                    continue
                if ".trash" in p.parts or ".cutemd" in p.parts:
                    continue

                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue

                cached = self._mtime_cache.get(p)
                if cached is not None and cached == mtime:
                    continue

                self._mtime_cache[p] = mtime

                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                for m in _TASK_RE.finditer(text):
                    checkbox = m.group(1)  # " " or "x"
                    task_text = m.group(2).strip()
                    if not task_text:
                        continue
                    lower = task_text.lower()
                    if self._task_kw in lower:
                        line_num = text[:m.start()].count("\n") + 1
                        self.task_found.emit(p, line_num, task_text, checkbox == "x")
        except Exception:
            _LOG.exception("TaskScanner: error during scan")

        _LOG.debug("TaskScanner: scan complete")
        self.scan_complete.emit()

    def invalidate(self) -> None:
        self._mtime_cache.clear()


class TasksPanel(QWidget):
    """Sidebar panel showing tasks grouped by done / not-done."""

    task_activated = Signal(Path, int)  # file_path, char_offset
    file_modified = Signal(Path)  # file_path, emitted after toggle

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-size: 11px; font-weight: bold; padding: 4px;")
        layout.addWidget(self._status_label)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setRootIsDecorated(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

        self._task_kw = _DEFAULT_TASK_KEYWORD
        self._folder_path: Path | None = None
        self._scanner: _TaskScanner | None = None
        self._debounce: QTimer | None = None

        # Persistent top-level items
        self._root_not_done = QTreeWidgetItem(self._tree)
        self._root_not_done.setText(0, self.tr("Not Done"))
        self._root_not_done.setFlags(self._root_not_done.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        f = self._root_not_done.font(0)
        f.setBold(True)
        self._root_not_done.setFont(0, f)
        self._root_not_done.setExpanded(True)

        self._root_done = QTreeWidgetItem(self._tree)
        self._root_done.setText(0, self.tr("Done"))
        self._root_done.setFlags(self._root_done.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self._root_done.setFont(0, f)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_keyword(self, keyword: str) -> None:
        self._task_kw = keyword or _DEFAULT_TASK_KEYWORD

    def set_folder(self, path: Path | None) -> None:
        self._folder_path = path
        self._cancel_scan()
        self._clear_items()
        if path is None:
            self._status_label.setText("")
            return
        self._status_label.setText(self.tr("Tasks: 0"))
        self._schedule_scan(full=True)

    def schedule_scan(self, full: bool = False) -> None:
        """Schedule a debounced scan (incremental by default, full if *full* is True)."""
        if self._folder_path is None:
            return
        self._schedule_scan(full=full)

    def clear(self) -> None:
        self._folder_path = None
        self._cancel_scan()
        self._clear_items()
        self._status_label.setText("")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clear_items(self) -> None:
        while self._root_not_done.childCount():
            self._root_not_done.removeChild(self._root_not_done.child(0))
        while self._root_done.childCount():
            self._root_done.removeChild(self._root_done.child(0))

    def _cancel_scan(self) -> None:
        if self._scanner is not None:
            try:
                if self._scanner.isRunning():
                    self._scanner.requestInterruption()
                    self._scanner.wait(2000)
            except RuntimeError:
                pass
        self._scanner = None

    def _schedule_scan(self, full: bool = False) -> None:
        if self._debounce is not None:
            self._debounce.stop()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(lambda: self._do_scan(full))
        self._debounce.start()

    def _do_scan(self, full: bool = False) -> None:
        if self._folder_path is None:
            return
        self._cancel_scan()

        if full:
            self._clear_items()

        self._status_label.setText(self.tr("Scanning\u2026"))
        self._scanner = _TaskScanner(self._folder_path, self._task_kw, self)
        if full:
            self._scanner.invalidate()
        self._scanner.task_found.connect(self._on_task_found)
        self._scanner.scan_complete.connect(self._on_scan_complete)
        self._scanner.finished.connect(self._on_scan_finished)
        self._scanner.start()

    def _on_task_found(self, file_path: Path, line_num: int, text: str, is_done: bool) -> None:
        root = self._root_done if is_done else self._root_not_done
        rel = str(file_path.relative_to(self._folder_path)) if self._folder_path else file_path.name
        display = f"{text}  \u2014 {rel}"
        item = QTreeWidgetItem(root)
        item.setText(0, display)
        item.setToolTip(0, str(file_path))
        item.setData(0, Qt.ItemDataRole.UserRole, (file_path, line_num))
        if not is_done:
            font = item.font(0)
            font.setStrikeOut(False)
            item.setFont(0, font)

    def _on_scan_complete(self) -> None:
        not_done = self._root_not_done.childCount()
        done = self._root_done.childCount()
        total = not_done + done
        self._root_not_done.setText(0, self.tr("Not Done ({})").format(not_done))
        self._root_done.setText(0, self.tr("Done ({})").format(done))
        self._status_label.setText(self.tr("Tasks: {}").format(total))
        _LOG.debug("Task scan complete: %d not done, %d done", not_done, done)

    def _on_scan_finished(self) -> None:
        self._scanner = None

    def _on_item_clicked(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is not None:
            file_path, line_num = data
            self.task_activated.emit(file_path, line_num)

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        menu = QMenu(self)
        act = QAction(self.tr("Toggle done / not done"), self)
        act.triggered.connect(lambda: self._toggle_task(item))
        menu.addAction(act)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _toggle_task(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        file_path, line_num = data
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        except OSError:
            return
        if line_num < 1 or line_num > len(lines):
            return
        idx = line_num - 1
        line = lines[idx]
        # Toggle [ ] <-> [x]
        if "- [ ]" in line:
            new_line = line.replace("- [ ]", "- [x]", 1)
        elif "- [x]" in line:
            new_line = line.replace("- [x]", "- [ ]", 1)
        else:
            return
        lines[idx] = new_line
        try:
            file_path.write_text("".join(lines), encoding="utf-8")
        except OSError:
            return
        self.file_modified.emit(file_path)
        self.schedule_scan(full=True)
