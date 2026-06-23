"""Search-in-files panel for the sidebar — non-blocking chunked search."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

_CHUNK_SIZE = 20
_CHUNK_INTERVAL = 10  # ms


class SearchPanel(QWidget):
    """Sidebar panel to search inside markdown files of the open folder."""

    file_activated = Signal(Path, int)  # file_path, line_number

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._folder_path: Path | None = None
        self._generator: object = None
        self._query: str = ""
        self._flags: int = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(self.tr("Search files\u2026"))
        self._search_input.textChanged.connect(self._on_search_text_changed)

        case_row = QHBoxLayout()
        self._search_case_cb = QCheckBox(self.tr("Match case"))
        self._search_case_cb.toggled.connect(
            lambda: self._on_search_text_changed(self._search_input.text())
        )
        case_row.addWidget(self._search_case_cb)
        case_row.addStretch()

        self._search_results = QListWidget()
        self._search_results.itemDoubleClicked.connect(self._on_search_result_clicked)

        layout.addWidget(self._search_input)
        layout.addLayout(case_row)
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
        self._timer.stop()
        self._generator = None
        self._search_results.clear()

        self._query = text
        if not text or self._folder_path is None:
            return

        self._flags = re.IGNORECASE if not self._search_case_cb.isChecked() else 0
        self._generator = self._folder_path.rglob("*.md")
        self._timer.start()

    def _process_chunk(self) -> None:
        query = self._query
        if not query or self._generator is None:
            self._timer.stop()
            return

        flags = self._flags
        results = self._search_results

        for _ in range(_CHUNK_SIZE):
            try:
                md_path = next(self._generator)  # type: ignore[arg-type]
            except StopIteration:
                self._timer.stop()
                self._generator = None
                return

            try:
                content = md_path.read_text(encoding="utf-8")
            except OSError:
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                if re.search(re.escape(query), line, flags):
                    rel = md_path.relative_to(self._folder_path)  # type: ignore[arg-type]
                    item_text = f"{rel}:{line_num}: {line.strip()[:120]}"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, (md_path, line_num))
                    results.addItem(item)

    def _on_search_result_clicked(self, item: QListWidgetItem) -> None:
        location = item.data(Qt.ItemDataRole.UserRole)
        if location:
            self.file_activated.emit(location[0], location[1])
