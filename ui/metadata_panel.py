"""Frontmatter metadata panel for the right dock."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class MetadataPanel(QFrame):
    """Displays frontmatter fields (title, date, tags, aliases) in a card."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metadataPanel")

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size: 14px; font-weight: bold;")

        self._fields_layout = QVBoxLayout()
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(4)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(10, 10, 10, 10)
        inner_layout.addWidget(self._title)
        inner_layout.addSpacing(8)
        inner_layout.addLayout(self._fields_layout)
        inner_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def show_metadata(self, fields: dict) -> None:
        """Display frontmatter *fields* dict."""
        # Clear previous
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        title = fields.get("title", "")
        if title:
            self._title.setText(str(title))
        else:
            self._title.setText("")

        shown: set[str] = set()
        for key in ("date", "tags", "aliases", "alias"):
            val = fields.get(key)
            if val is None or (isinstance(val, (list, str)) and not val):
                continue
            shown.add(key)
            self._add_row(key, val)

        # Show remaining fields
        for key, val in fields.items():
            if key in shown or key == "title":
                continue
            self._add_row(key, val)

    def _add_row(self, key: str, val: object) -> None:
        """Add a key: value row."""
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(0)

        key_lbl = QLabel(str(key).capitalize())
        key_lbl.setStyleSheet("font-size: 10px; font-weight: bold;")

        if isinstance(val, list):
            val_lbl = QLabel(", ".join(str(v) for v in val))
        else:
            val_lbl = QLabel(str(val))
        val_lbl.setWordWrap(True)
        val_lbl.setStyleSheet("font-size: 12px;")

        row_layout.addWidget(key_lbl)
        row_layout.addWidget(val_lbl)
        self._fields_layout.addWidget(row)

    def clear(self) -> None:
        self._title.setText("")
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
