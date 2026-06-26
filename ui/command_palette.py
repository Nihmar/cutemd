"""Searchable command palette — triggered by Ctrl+P."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidgetItem,
    QVBoxLayout,
)

from ui.shortcuts_dialog import _SHORTCUT_CATEGORIES, _shortcut_text
from ui.widgets import CuteListWidget

_CAT_ORDER = {
    "File": 0,
    "Edit": 1,
    "View": 2,
    "Settings": 3,
    "Help": 4,
    "Other": 99,
}


class CommandPalette(QDialog):
    """A fuzzy-search command palette à la VS Code / Obsidian."""

    _W = 500
    _H = 360

    def __init__(self, actions: dict[str, QAction], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Commands"))
        self.setFixedSize(self._W, self._H)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("""
            CommandPalette {
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(window);
            }
            QLineEdit {
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 4px 6px;
            }
            QListWidget {
                background: palette(base);
                border: none;
                outline: none;
            }
            QListWidget::item {
                min-height: 24px;
                padding: 0 6px;
                border-radius: 3px;
            }
            QListWidget::item:hover,
            QListWidget::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
        """)

        self._actions = actions

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText(self.tr("Type a command\u2026"))
        self._input.textChanged.connect(self._apply_filter)
        layout.addWidget(self._input)

        self._list = CuteListWidget()
        self._list.setFrameShape(CuteListWidget.Shape.NoFrame)
        layout.addWidget(self._list)

        self._build_items()

        self._input.setFocus()
        self._list.itemClicked.connect(self._execute)
        self._list.itemActivated.connect(self._execute)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def exec(self):
        # Center over parent.
        if self.parent() is not None:
            parent_geo = self.parent().window().geometry()
            x = parent_geo.center().x() - self._W // 2
            y = parent_geo.center().y() - self._H // 2
            self.move(x, y)

        self._input.selectAll()

        # Defer focus so the dialog is visible first.
        QTimer.singleShot(0, self._input.setFocus)
        return super().exec()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return
        key = event.key()
        if key == Qt.Key.Key_Down:
            self._select_next(1)
        elif key == Qt.Key.Key_Up:
            self._select_next(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._list.currentItem()
            if item and not item.isHidden():
                self._execute(item)
        elif key == Qt.Key.Key_Escape:
            self.reject()
        else:
            # Let the search input handle the character.
            self._input.setFocus()
            super().keyPressEvent(event)

    def _select_next(self, direction: int) -> None:
        row = self._list.currentRow()
        count = self._list.count()
        step = direction
        while 0 <= row + step < count:
            row += step
            item = self._list.item(row)
            if item and not item.isHidden():
                self._list.setCurrentRow(row)
                return

    # ------------------------------------------------------------------
    # Internal

    def _build_items(self) -> None:
        rows: list[tuple[str, str, str, QAction]] = []
        for name, action in self._actions.items():
            text = action.text().replace("&", "")
            shortcut = _shortcut_text(action)
            cat = _SHORTCUT_CATEGORIES.get(name, self.tr("Other"))
            rows.append((text, shortcut, cat, action))

        rows.sort(key=lambda r: (_CAT_ORDER.get(r[2], 99), r[0]))

        for text, shortcut, cat, action in rows:
            display = text
            if shortcut:
                display += f"  ({shortcut})"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, action)
            item.setData(Qt.ItemDataRole.UserRole + 1, cat)
            self._list.addItem(item)

    def _apply_filter(self, text: str) -> None:
        ft = text.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            visible = (not ft) or (ft in item.text().lower())
            item.setHidden(not visible)
        # Select first visible
        for i in range(self._list.count()):
            if not self._list.item(i).isHidden():
                self._list.setCurrentRow(i)
                break

    def _execute(self, item: QListWidgetItem) -> None:
        action: QAction | None = item.data(Qt.ItemDataRole.UserRole)
        if action is not None and action.isEnabled():
            self.accept()
            # Use a short timer so the dialog closes before the action runs.
            QTimer.singleShot(0, action.trigger)
