"""Search-in-files panel for the sidebar — non-blocking chunked search
with replace functionality."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.logging import setup_logging
from ui.widgets import CuteListWidget

_CHUNK_SIZE = 20
_CHUNK_INTERVAL = 10  # ms

_LOG = setup_logging("cutemd.search")


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
        case_row.addStretch()

        # --- Buttons ---
        self._replace_btn = QPushButton(self.tr("Replace"))
        self._replace_btn.clicked.connect(self._replace_single)

        self._replace_all_btn = QPushButton(self.tr("Replace All"))
        self._replace_all_btn.clicked.connect(self._replace_all_in_files)

        self._count_label = QLabel()

        # --- Results ---
        self._search_results = CuteListWidget()
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
        self._timer.setInterval(_CHUNK_INTERVAL)
        self._timer.timeout.connect(self._process_chunk)

    def set_folder(self, path: Path | None) -> None:
        self._folder_path = path
        self._timer.stop()
        self._generator = None
        self._search_results.clear()
        self._search_input.clear()

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _on_search_text_changed(self, text: str) -> None:
        _LOG.debug("_on_search_text_changed: pattern=%s", text)
        self._timer.stop()
        self._generator = None
        self._search_results.clear()

        self._query = text
        if not text or self._folder_path is None:
            self._count_label.setText("")
            return

        self._flags = re.IGNORECASE if not self._search_case_cb.isChecked() else 0
        self._compiled_pattern = re.compile(re.escape(text), self._flags)
        self._generator = self._folder_path.rglob("*.md")
        self._timer.start()

    def _process_chunk(self) -> None:
        """Process one chunk of files from the rglob generator.

        This method is called periodically by a QTimer. It pulls up to
        ``_CHUNK_SIZE`` files from the generator, reads each one, and
        performs a regex search (with ``re.escape`` for literal matching)
        across every line. Matches are accumulated into the results
        ``CuteListWidget`` as ``QListWidgetItem`` items, each storing the
        file path and line number in ``UserRole`` data. Once the generator
        is exhausted the timer stops and the count label is updated.
        """
        _LOG.debug("_process_chunk: searching")
        query = self._query
        if not query or self._generator is None:
            self._timer.stop()
            return

        pattern = self._compiled_pattern
        results = self._search_results

        for _ in range(_CHUNK_SIZE):
            try:
                md_path = next(self._generator)  # type: ignore[arg-type]
            except StopIteration:
                self._timer.stop()
                self._generator = None
                self._update_count()
                _LOG.debug("_process_chunk: found %d matches", results.count())
                return

            try:
                content = md_path.read_text(encoding="utf-8")
            except OSError:
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    rel = md_path.relative_to(self._folder_path)  # type: ignore[arg-type]
                    item_text = f"{rel}:{line_num}: {line.strip()[:120]}"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, (md_path, line_num))
                    results.addItem(item)

        self._update_count()
        _LOG.debug("_process_chunk: found %d matches", results.count())

    def _update_count(self) -> None:
        count = self._search_results.count()
        self._count_label.setText(self.tr("{} matches").format(count))

    def _on_search_result_clicked(self, item: QListWidgetItem) -> None:
        location = item.data(Qt.ItemDataRole.UserRole)
        if location:
            self.file_activated.emit(location[0], location[1])

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            if obj is self._search_results:
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    item = self._search_results.currentItem()
                    if item:
                        self._on_search_result_clicked(item)
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self._search_input.setFocus()
                    self._search_input.selectAll()
                    return True
            elif obj is self._search_input:
                if event.key() == Qt.Key.Key_Down:
                    self._search_results.setFocus()
                    if self._search_results.count() > 0:
                        self._search_results.setCurrentRow(0)
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

        location = item.data(Qt.ItemDataRole.UserRole)
        if not location:
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
        new_line, count = re.subn(re.escape(query), replacement, line, count=1, flags=flags)

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
        rel = file_path.relative_to(self._folder_path)  # type: ignore[arg-type]
        item.setText(f"{rel}:{line_num}: {new_line.strip()[:120]}")
        item.setData(Qt.ItemDataRole.UserRole, None)  # mark as replaced

    def _replace_all_in_files(self) -> None:
        """Replace all occurrences across all files in the search results."""
        query = self._search_input.text()
        replacement = self._replace_input.text()
        if not query:
            return

        count = self._search_results.count()
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
        replaced_total = 0
        files_modified: list[Path] = []

        # Collect all results grouped by file
        file_results: dict[Path, list[int]] = {}
        for i in range(self._search_results.count()):
            item = self._search_results.item(i)
            if item is None:
                continue
            location = item.data(Qt.ItemDataRole.UserRole)
            if location is None:
                continue
            file_path, line_num = location
            file_results.setdefault(file_path, []).append(line_num)

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
                    re.escape(query), replacement, lines[line_num - 1], flags=flags
                )
                if count > 0:
                    lines[line_num - 1] = new_line
                    file_replaced += count

            if file_replaced > 0:
                try:
                    file_path.write_text("\n".join(lines), encoding="utf-8")
                    replaced_total += file_replaced
                    files_modified.append(file_path)
                except OSError as e:
                    QMessageBox.critical(
                        self,
                        self.tr("Error"),
                        self.tr("Could not write file {}:\n{}").format(file_path.name, e),
                    )

        QMessageBox.information(
            self,
            self.tr("Replace All"),
            self.tr("Replaced {} occurrences in {} files.").format(
                replaced_total, len(files_modified)
            ),
        )

        # Refresh search results
        self._on_search_text_changed(self._search_input.text())

    def _get_affected_files(self) -> set[Path]:
        """Return the set of unique file paths in the results."""
        files: set[Path] = set()
        for i in range(self._search_results.count()):
            item = self._search_results.item(i)
            if item is None:
                continue
            location = item.data(Qt.ItemDataRole.UserRole)
            if location:
                files.add(location[0])
        return files
