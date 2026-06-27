"""Keyboard shortcuts reference dialog."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.constants import CATEGORY_ORDER, SHORTCUT_CATEGORIES


def _shortcut_text(action: QAction) -> str:
    seq = action.shortcut()
    if not seq.isEmpty():
        return seq.toString(QKeySequence.SequenceFormat.NativeText)
    # Fallback: check data property (set by ShortcutManager for actions
    # whose QAction shortcut was cleared in favour of a QShortcut).
    val = action.data()
    if isinstance(val, str) and val:
        return val
    return ""



class ShortcutsDialog(QDialog):
    """Shows a read-only table of all keyboard shortcuts."""

    def __init__(self, actions: dict[str, QAction], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Keyboard Shortcuts"))
        self.setMinimumWidth(520)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels([
            self.tr("Action"), self.tr("Category"), self.tr("Shortcut"),
        ])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)

        rows = []
        for name, action in actions.items():
            text = action.text().replace("&", "")
            shortcut = _shortcut_text(action)
            cat = SHORTCUT_CATEGORIES.get(name, self.tr("Other"))
            rows.append((text, cat, shortcut))

        rows.sort(key=lambda r: (CATEGORY_ORDER.get(r[1], 99), r[0]))
        table.setRowCount(len(rows))
        for i, (text, cat, shortcut) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(text))
            table.setItem(i, 1, QTableWidgetItem(self.tr(cat)))
            table.setItem(i, 2, QTableWidgetItem(shortcut))

        layout.addWidget(table)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
