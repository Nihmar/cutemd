"""Frontmatter metadata panel for the right dock."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class MetadataPanel(QFrame):
    """Displays frontmatter fields (title, date, tags, aliases)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._header = QLabel()
        self._header.setObjectName("metadataPanelHeader")
        self._header.setStyleSheet("font-size: 11px; font-weight: bold; padding: 4px;")

        self._fields_layout = QVBoxLayout()
        self._fields_layout.setContentsMargins(4, 0, 4, 0)
        self._fields_layout.setSpacing(4)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.addWidget(self._header)
        inner_layout.addLayout(self._fields_layout)
        inner_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(scroll)

    def show_metadata(self, fields: dict) -> None:
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        shown = {k: v for k, v in fields.items() if v or v == 0}
        if not shown:
            self._header.setText("")
            return

        self._header.setText(self.tr("Frontmatter"))

        for key in ("title", "date", "tags", "aliases", "alias"):
            val = shown.pop(key, None)
            if val is None:
                continue
            self._add_row(key, val)

        for key, val in shown.items():
            self._add_row(key, val)

    def _add_row(self, key: str, val: object) -> None:
        key_lbl = QLabel(f"{key}:")
        key_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")

        if isinstance(val, list):
            val_str = ", ".join(str(v) for v in val)
        else:
            val_str = str(val)

        val_lbl = QLabel(val_str)
        val_lbl.setWordWrap(True)
        val_lbl.setStyleSheet("font-size: 13px;")

        row = QVBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(0)
        row.addWidget(key_lbl)
        row.addWidget(val_lbl)

        wrapper = QWidget()
        wrapper.setLayout(row)
        self._fields_layout.addWidget(wrapper)

    def clear(self) -> None:
        self._header.setText("")
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
