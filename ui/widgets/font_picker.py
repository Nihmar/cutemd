"""Font picker widget — searchable list with live font preview.

Extracted from SettingsDialog so it can be reused (e.g., in a
standalone font-selection dialog).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidgetItem,
    QSizePolicy,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import CuteListWidget


class FontPreviewDelegate(QStyledItemDelegate):
    """Creates QFont lazily for visible items only."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        data = index.data(Qt.ItemDataRole.UserRole)
        if data and data != "System":
            font = QFont(index.data(Qt.ItemDataRole.DisplayRole))
            font.setPointSize(option.font.pointSize())
            option.font = font


class FontPicker(QWidget):
    """A searchable font-family picker with inline preview."""

    _LIST_HEIGHT = 150

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._edit = QLineEdit()
        self._edit.setClearButtonEnabled(True)
        lay.addWidget(self._edit)

        self._list = CuteListWidget()
        self._list.setFrameShape(CuteListWidget.Shape.NoFrame)
        self._list.setFixedHeight(self._LIST_HEIGHT)
        self._list.setItemDelegate(FontPreviewDelegate(self._list))
        lay.addWidget(self._list)

        edit_h = self._edit.sizeHint().height()
        total_h = edit_h + lay.spacing() + self._LIST_HEIGHT
        self.setMaximumHeight(total_h)

        sp = self.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        self.setSizePolicy(sp)

        self._edit.textChanged.connect(self._apply_filter)

    def add_item(self, text: str, data: str) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, data)
        self._list.addItem(item)
        return item

    def select_by_data(self, data: str) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == data:
                self._list.setCurrentRow(i)
                self._list.scrollToItem(item)
                return
        if self._list.count():
            self._list.setCurrentRow(0)

    def select_first(self) -> None:
        self._edit.clear()
        if self._list.count():
            self._list.setCurrentRow(0)
            self._list.scrollToItem(self._list.item(0))

    def _apply_filter(self, text: str) -> None:
        ft = text.lower()
        first_visible = None
        for i in range(self._list.count()):
            item = self._list.item(i)
            visible = (not ft) or (ft in item.text().lower())
            item.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = item
        cur = self._list.currentItem()
        if cur is None or cur.isHidden():
            if first_visible is not None:
                self._list.setCurrentItem(first_visible)
                self._list.scrollToItem(first_visible)

    def current_data(self) -> str:
        item = self._list.currentItem()
        if item is not None:
            return item.data(Qt.ItemDataRole.UserRole)
        return "System"
