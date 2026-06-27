"""Table of Contents panel — shows headings of the current document."""

import re
from pathlib import Path

from core.logging import setup_logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QListWidgetItem, QVBoxLayout, QWidget

from ui.widgets import CuteListWidget

_LOG = setup_logging("cutemd.toc")
_RE_HEADING = re.compile(r"^(#{1,6})\s+(.+)")


class TocPanel(QWidget):
    """Sidebar panel that lists headings from the current editor tab.

    Clicking a heading scrolls the editor to that line.
    """

    heading_activated = Signal(int)  # line number (0-based)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._header = QLabel(self.tr("Table of Contents"))
        self._header.setStyleSheet("font-size: 11px; font-weight: bold; padding: 4px;")
        layout.addWidget(self._header)

        self._list = CuteListWidget()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rebuild(self, text: str) -> None:
        """Parse *text* and rebuild the heading list."""
        self._list.clear()
        lines = text.split("\n")
        self._entries: list[tuple[str, int, int]] = []  # (display_text, line, level)

        for line_num, line in enumerate(lines):
            m = _RE_HEADING.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                display = ("  " * (level - 1)) + title
                self._entries.append((title, line_num, level))

                item = QListWidgetItem(display)
                font = item.font()
                font.setBold(level == 1)
                item.setFont(font)
                item.setData(Qt.ItemDataRole.UserRole, line_num)
                self._list.addItem(item)

        _LOG.debug("rebuild: %d headings", len(self._entries))
        self._header.setText(
            self.tr("Table of Contents ({})").format(len(self._entries))
        )

    def clear(self) -> None:
        """Clear the heading list."""
        _LOG.debug("clear")
        self._list.clear()
        self._entries = []
        self._header.setText(self.tr("Table of Contents (0)"))

    def has_entries(self) -> bool:
        return self._list.count() > 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        line = item.data(Qt.ItemDataRole.UserRole)
        if line is not None:
            self.heading_activated.emit(line)
