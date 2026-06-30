"""Search-in-files panel for the sidebar — non-blocking chunked search
with replace functionality."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.logging import setup_logging

_LOG = setup_logging("cutemd.search_panel")

_RG_AVAILABLE: bool | None = None  # cached availability check


def _check_rg() -> bool:
    """Return True if ripgrep is available on the system PATH."""
    global _RG_AVAILABLE
    if _RG_AVAILABLE is None:
        import shutil
        _RG_AVAILABLE = shutil.which("rg") is not None
        if _RG_AVAILABLE:
            _LOG.debug("ripgrep (rg) found — using for find-in-files")
    return _RG_AVAILABLE


def _rg_search(folder: Path, pattern: str, flags: int, regex_mode: bool) -> list[tuple[Path, int, str]]:
    """Run ripgrep and return [(file_path, line_num, line_text), ...]."""
    import subprocess
    args = ["rg", "--line-number", "--no-heading", "--color", "never", "-g", "*.md"]
    if flags & re.IGNORECASE:
        args.append("-i")
    if not regex_mode:
        args.append("-F")  # fixed-string search
    args.append(pattern)
    args.append(str(folder))
    try:
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    results: list[tuple[Path, int, str]] = []
    if proc.stdout is None:
        return results
    for line in proc.stdout.splitlines():
        parts = line.rsplit(":", 2)
        if len(parts) >= 3:
            try:
                file_path = Path(parts[0])
                line_num = int(parts[1])
                line_text = parts[2].strip()[:120]
                results.append((file_path, line_num, line_text))
            except (ValueError, OSError):
                continue
    return results

_CHUNK_SIZE = 20
_CHUNK_INTERVAL = 10  # ms


class _ReplaceWorker(QObject):
    """Runs replace-all in a background thread."""
    done = Signal(int, object)

    def __init__(self, query: str, replacement: str, flags: int,
                 file_results: dict, regex_mode: bool = False, parent=None):
        super().__init__(parent)
        self._query = query
        self._replacement = replacement
        self._flags = flags
        self._file_results = file_results
        self._regex_mode = regex_mode

    def run(self) -> None:
        replaced, files = _do_replace_in_files(
            self._file_results, self._query, self._replacement,
            self._flags, self._regex_mode
        )
        self.done.emit(replaced, files)


def _do_replace_in_files(
    file_results: dict, query: str, replacement: str, flags: int,
    regex_mode: bool = False,
) -> tuple[int, list]:
    """Pure function — performs the actual replace across files."""
    pattern = query if regex_mode else re.escape(query)
    replaced_total = 0
    files_modified: list = []
    for file_path, line_nums in file_results.items():
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = content.split("\n")
        file_replaced = 0
        for line_num in sorted(set(line_nums)):
            if line_num < 1 or line_num > len(lines):
                continue
            new_line, count = re.subn(
                pattern, replacement, lines[line_num - 1], flags=flags
            )
            if count > 0:
                lines[line_num - 1] = new_line
                file_replaced += count
        if file_replaced > 0:
            try:
                file_path.write_text("\n".join(lines), encoding="utf-8")
                replaced_total += file_replaced
                files_modified.append(file_path)
            except OSError:
                pass
    return replaced_total, files_modified

_ERROR_COLOR = "#e06c75"
_ERROR_SS = f"border: 1px solid {_ERROR_COLOR};"


class SearchPanel(QWidget):
    """Sidebar panel to search inside markdown files of the open folder,
    with optional replace-in-files support."""

    file_activated = Signal(Path, int)  # file_path, line_number

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._folder_path: Path | None = None
        self._generator: object = None
        self._query: str = ""
        self._flags: int = 0
        self._compiled_pattern: re.Pattern[str] | None = None
        self._result_count: int = 0
        self._file_items: dict[Path, QTreeWidgetItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # --- Search input ---
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(self.tr("Search files\u2026"))
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._search_input.installEventFilter(self)

        # --- Replace input ---
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText(self.tr("Replace\u2026"))

        # --- Options row ---
        case_row = QHBoxLayout()
        self._search_case_cb = QCheckBox(self.tr("Match case"))
        self._search_case_cb.toggled.connect(
            lambda: self._on_search_text_changed(self._search_input.text())
        )
        case_row.addWidget(self._search_case_cb)
        self._search_regex_cb = QCheckBox(self.tr("Regex"))
        self._search_regex_cb.toggled.connect(
            lambda: self._on_search_text_changed(self._search_input.text())
        )
        case_row.addWidget(self._search_regex_cb)
        case_row.addStretch()

        # --- Buttons ---
        self._replace_btn = QPushButton(self.tr("Replace"))
        self._replace_btn.clicked.connect(self._replace_single)

        self._replace_all_btn = QPushButton(self.tr("Replace All"))
        self._replace_all_btn.clicked.connect(self._replace_all_in_files)

        self._count_label = QLabel()

        # --- Results ---
        self._search_results = QTreeWidget()
        self._search_results.setHeaderHidden(True)
        self._search_results.setIndentation(16)
        self._search_results.setRootIsDecorated(True)
        self._search_results.itemDoubleClicked.connect(self._on_search_result_clicked)
        self._search_results.installEventFilter(self)

        layout.addWidget(self._search_input)
        layout.addWidget(self._replace_input)
        layout.addLayout(case_row)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._replace_btn)
        btn_row.addWidget(self._replace_all_btn)
        btn_row.addWidget(self._count_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addWidget(self._search_results)

        # Chunked search timer
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_CHUNK_INTERVAL)
        self._timer.timeout.connect(self._process_chunk)

    def set_folder(self, path: Path | None) -> None:
        self._folder_path = path
        self._timer.stop()
        self._generator = None
        self._search_results.clear()
        self._file_items.clear()
        self._result_count = 0
        self._search_input.clear()

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _on_search_text_changed(self, text: str) -> None:
        _LOG.debug("_on_search_text_changed: pattern=%s", text)
        self._timer.stop()
        self._generator = None
        self._search_results.clear()
        self._file_items.clear()
        self._result_count = 0

        self._query = text
        if not text or self._folder_path is None:
            self._count_label.setText("")
            return

        self._flags = re.IGNORECASE if not self._search_case_cb.isChecked() else 0
        use_regex = self._search_regex_cb.isChecked()
        try:
            self._compiled_pattern = re.compile(
                text if use_regex else re.escape(text), self._flags
            )
            self._search_input.setStyleSheet("")
            self._regex_valid = True
        except re.error:
            self._compiled_pattern = None
            self._search_input.setStyleSheet(_ERROR_SS)
            self._regex_valid = False
            return

        self._generator = self._folder_path.rglob("*.md")
        self._timer.start()

    def _process_chunk(self) -> None:
        """Process one chunk of files from the rglob generator.

        Uses ripgrep (rg) if available on the system — otherwise falls
        back to a chunked Python regex scan.
        """
        query = self._query
        if not query or self._folder_path is None:
            self._timer.stop()
            return

        # Fast path: ripgrep backend.
        if _check_rg() and self._generator is not None:
            self._timer.stop()
            self._generator = None
            self._search_results.clear()
            self._file_items.clear()
            self._result_count = 0
            results = _rg_search(
                self._folder_path, query, self._flags,
                self._search_regex_cb.isChecked(),
            )
            for file_path, line_num, line_text in results:
                self._add_result(file_path, line_num, line_text)
            self._update_count()
            return

        # Fallback: chunked Python scan.
        if self._generator is None:
            self._timer.stop()
            return

        pattern = self._compiled_pattern

        for _ in range(_CHUNK_SIZE):
            try:
                md_path = next(self._generator)
            except StopIteration:
                self._timer.stop()
                self._generator = None
                self._update_count()
                return

            if ".trash" in md_path.parts or ".cutemd" in md_path.parts:
                continue

            try:
                content = md_path.read_text(encoding="utf-8")
            except OSError:
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    self._add_result(md_path, line_num, line.strip()[:120])

        self._update_count()
        _LOG.debug("_process_chunk: found %d matches", self._result_count)

    def _add_result(self, file_path: Path, line_num: int, line_text: str) -> None:
        """Add a single search result as a child item under a file group."""
        tree = self._search_results
        key = file_path.resolve()
        if key not in self._file_items:
            try:
                rel = file_path.relative_to(self._folder_path)
            except ValueError:
                rel = file_path
            parent = QTreeWidgetItem(tree)
            parent.setText(0, str(rel))
            parent.setData(0, Qt.ItemDataRole.UserRole, (file_path, 0))
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsAutoTristate)
            self._file_items[key] = parent
        parent = self._file_items[key]
        child = QTreeWidgetItem(parent)
        child.setText(0, f"{line_num}: {line_text}")
        child.setData(0, Qt.ItemDataRole.UserRole, (file_path, line_num))
        self._result_count += 1

    def _update_count(self) -> None:
        self._count_label.setText(self.tr("{} matches").format(self._result_count))

    def _on_search_result_clicked(self, item: QTreeWidgetItem) -> None:
        location = item.data(0, Qt.ItemDataRole.UserRole)
        if location and location[1] > 0:
            self.file_activated.emit(location[0], location[1])

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            if obj is self._search_results:
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    item = self._search_results.currentItem()
                    if item and item.data(0, Qt.ItemDataRole.UserRole) is not None:
                        self._on_search_result_clicked(item)
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self._search_input.setFocus()
                    self._search_input.selectAll()
                    return True
            elif obj is self._search_input:
                if event.key() == Qt.Key.Key_Down:
                    self._search_results.setFocus()
                    if self._search_results.topLevelItemCount() > 0:
                        top = self._search_results.topLevelItem(0)
                        self._search_results.setCurrentItem(top)
                    return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Replace
    # ------------------------------------------------------------------
    def _replace_single(self) -> None:
        """Replace the query in the selected result's file at the given line."""
        query = self._search_input.text()
        replacement = self._replace_input.text()
        if not query:
            return

        item = self._search_results.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                self.tr("Replace"),
                self.tr("Select a match from the results list first."),
            )
            return

        location = item.data(0, Qt.ItemDataRole.UserRole)
        if not location or location[1] == 0:
            return

        file_path, line_num = location
        _LOG.debug("_replace_single: %s line %d", file_path, line_num)
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(
                self, self.tr("Error"), self.tr("Could not read file:\n{}").format(e)
            )
            return

        lines = content.split("\n")
        if line_num < 1 or line_num > len(lines):
            return

        line = lines[line_num - 1]
        flags = re.IGNORECASE if not self._search_case_cb.isChecked() else 0
        pattern = query if self._search_regex_cb.isChecked() else re.escape(query)
        try:
            new_line, count = re.subn(pattern, replacement, line, count=1, flags=flags)
        except re.error:
            return

        if count == 0:
            QMessageBox.information(
                self,
                self.tr("Replace"),
                self.tr("Match not found (file may have changed)."),
            )
            return

        lines[line_num - 1] = new_line
        try:
            file_path.write_text("\n".join(lines), encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(
                self, self.tr("Error"), self.tr("Could not write file:\n{}").format(e)
            )
            return

        # Update the result item text
        item.setText(0, f"{line_num}: {new_line.strip()[:120]}")
        item.setData(0, Qt.ItemDataRole.UserRole, None)  # mark as replaced

    def _replace_all_in_files(self) -> None:
        """Replace all occurrences across all files in the search results."""
        query = self._search_input.text()
        replacement = self._replace_input.text()
        if not query:
            return

        count = self._result_count
        if count == 0:
            return

        _LOG.debug("_replace_all_in_files: %d files", len(self._get_affected_files()))

        confirm = QMessageBox.question(
            self,
            self.tr("Replace All"),
            self.tr("Replace {} occurrences across {} files?").format(
                count, len(self._get_affected_files())
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        flags = re.IGNORECASE if not self._search_case_cb.isChecked() else 0

        # Collect all results grouped by file from the tree
        file_results: dict[Path, list[int]] = {}
        tree = self._search_results
        for i in range(tree.topLevelItemCount()):
            parent = tree.topLevelItem(i)
            if parent is None:
                continue
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child is None:
                    continue
                loc = child.data(0, Qt.ItemDataRole.UserRole)
                if loc is None or loc[1] == 0:
                    continue
                file_path, line_num = loc
                file_results.setdefault(file_path, []).append(line_num)

        # Run replace in background thread.
        self._replace_thread = QThread(self)
        self._replace_worker = _ReplaceWorker(query, replacement, flags, file_results,
                                              regex_mode=self._search_regex_cb.isChecked())
        self._replace_worker.moveToThread(self._replace_thread)
        self._replace_worker.done.connect(self._on_replace_done)
        self._replace_worker.done.connect(self._replace_thread.quit)
        self._replace_thread.started.connect(self._replace_worker.run)
        self._replace_thread.start()
        self._replace_btn.setEnabled(False)
        self._replace_all_btn.setEnabled(False)
        self._replace_all_btn.setText(self.tr("Replacing\u2026"))

    def _on_replace_done(self, replaced_total: int, files_modified: list) -> None:
        self._replace_btn.setEnabled(True)
        self._replace_all_btn.setEnabled(True)
        self._replace_all_btn.setText(self.tr("Replace All"))
        QMessageBox.information(
            self,
            self.tr("Replace All"),
            self.tr("Replaced {} occurrences in {} files.").format(
                replaced_total, len(files_modified)
            ),
        )
        self._on_search_text_changed(self._search_input.text())

    def _get_affected_files(self) -> set[Path]:
        """Return the set of unique file paths in the results."""
        files: set[Path] = set()
        tree = self._search_results
        for i in range(tree.topLevelItemCount()):
            parent = tree.topLevelItem(i)
            if parent is not None:
                loc = parent.data(0, Qt.ItemDataRole.UserRole)
                if loc:
                    files.add(loc[0])
        return files
