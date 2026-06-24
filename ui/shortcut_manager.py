"""Keyboard shortcut management — global defaults + per-folder overrides."""

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QKeySequence

if TYPE_CHECKING:
    from ui.folder_settings import FolderSettings


DEFAULT_SHORTCUTS: dict[str, str] = {
    "act_open_folder": "Ctrl+O",
    "act_new": "Ctrl+N",
    "act_save": "Ctrl+S",
    "act_save_as": "Ctrl+Shift+S",
    "act_close_tab": "Ctrl+W",
    "act_exit": "Ctrl+Q",
    "act_undo": "Ctrl+Z",
    "act_redo": "Ctrl+Shift+Z",
    "act_find": "Ctrl+F",
    "act_find_files": "Ctrl+Shift+F",
    "act_replace_files": "Ctrl+Shift+H",
    "act_toggle_preview": "Ctrl+P",
    "act_toggle_tree": "Ctrl+B",
    "act_settings": "Ctrl+,",
    "act_shortcuts": "Ctrl+/",
    "act_zoom_in": "Ctrl+=",
    "act_zoom_out": "Ctrl+-",
    "act_zoom_reset": "Ctrl+0",
    "act_zoom_preview_in": "Ctrl+Shift+=",
    "act_zoom_preview_out": "Ctrl+Shift+-",
}


class ShortcutManager:
    """Load per-folder shortcuts and apply them to QActions."""

    def __init__(self, folder_settings: "FolderSettings | None" = None) -> None:
        self._folder_settings = folder_settings

    def apply(self, actions: dict[str, QAction]) -> None:
        customs: dict[str, str] = {}
        if self._folder_settings is not None:
            customs = self._folder_settings.load_shortcuts()
        for name, action in actions.items():
            shortcut = customs.get(name) or DEFAULT_SHORTCUTS.get(name)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            else:
                action.setShortcut(QKeySequence())
