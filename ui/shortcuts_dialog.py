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


def _shortcut_text(action: QAction) -> str:
    seq = action.shortcut()
    return seq.toString(QKeySequence.SequenceFormat.NativeText) if not seq.isEmpty() else ""


_SHORTCUT_CATEGORIES: dict[str, str] = {
    "act_open_folder": "File",
    "act_close_folder": "File",
    "act_new": "File",
    "act_save": "File",
    "act_save_as": "File",
    "act_close_tab": "File",
    "act_exit": "File",
    "act_undo": "Edit",
    "act_redo": "Edit",
    "act_find": "Edit",
    "act_find_files": "Edit",
    "act_replace_files": "Edit",
    "act_toggle_preview": "View",
    "act_toggle_split": "View",
    "act_toggle_tree": "View",
    "act_toggle_statusbar": "View",
    "act_zoom_in": "View",
    "act_zoom_out": "View",
    "act_zoom_reset": "View",
    "act_zoom_preview_in": "View",
    "act_zoom_preview_out": "View",
    "act_webdav_sync": "File",
    "act_check_update": "Help",
    "act_command_palette": "Help",
    "act_settings": "Settings",
    "act_shortcuts": "Help",
}

_CAT_ORDER = {"File": 0, "Edit": 1, "View": 2, "Settings": 3, "Help": 4}


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
            cat = _SHORTCUT_CATEGORIES.get(name, self.tr("Other"))
            rows.append((text, cat, shortcut))

        rows.sort(key=lambda r: (_CAT_ORDER.get(r[1], 99), r[0]))
        table.setRowCount(len(rows))
        for i, (text, cat, shortcut) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(text))
            table.setItem(i, 1, QTableWidgetItem(self.tr(cat)))
            table.setItem(i, 2, QTableWidgetItem(shortcut))

        layout.addWidget(table)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
