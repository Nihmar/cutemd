"""Keyboard shortcut management — global defaults + per-folder overrides.

Shortcuts are handled by standalone QShortcut objects rather than
QAction.setShortcut().  This ensures they work on all platforms
regardless of menu-bar visibility or Qt platform plugins.
The QAction retains the shortcut *string* (via setData) so that the
ShortcutsDialog / CommandPalette can still display it.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

from core.logging import setup_logging

if TYPE_CHECKING:
    from core.folder_settings import FolderSettings

_LOG = setup_logging("cutemd.shortcut_manager")


DEFAULT_SHORTCUTS: dict[str, str] = {
    "act_open_folder": "Ctrl+O",
    "act_close_folder": "Ctrl+Shift+O",
    "act_new": "Ctrl+N",
    "act_new_from_template": "Ctrl+Shift+N",
    "act_daily_note": "Ctrl+Shift+D",
    "act_toggle_zen_mode": "F11",
    "act_save": "Ctrl+S",
    "act_save_as": "Ctrl+Shift+S",
    "act_close_tab": "Ctrl+W",
    "act_exit": "Ctrl+Q",
    "act_undo": "Ctrl+Z",
    "act_redo": "Ctrl+Shift+Z",
    "act_find": "Ctrl+F",
    "act_find_files": "Ctrl+Shift+F",
    "act_replace_files": "Ctrl+Shift+H",
    "act_toggle_preview": "Ctrl+Shift+P",
    "act_toggle_tree": "Ctrl+B",
    "act_toggle_tags": "Ctrl+Shift+T",
    "act_toggle_statusbar": "Ctrl+Shift+B",
    "act_command_palette": "Ctrl+P",
    "act_settings": "Ctrl+,",
    "act_shortcuts": "Ctrl+/",
    "act_webdav_sync": "Ctrl+Shift+Y",
    "act_zoom_in": "Ctrl+=",
    "act_zoom_out": "Ctrl+-",
    "act_zoom_reset": "Ctrl+0",
    "act_zoom_preview_in": "Ctrl+Shift+=",
    "act_zoom_preview_out": "Ctrl+Shift+-",
}


class ShortcutManager:
    """Create standalone QShortcuts wired to QAction.trigger signals."""

    def __init__(
        self,
        folder_settings: "FolderSettings | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        self._folder_settings = folder_settings
        self._parent = parent
        self._shortcuts: list[QShortcut] = []

    def apply(self, actions: dict[str, QAction]) -> None:
        customs: dict[str, str] = {}
        if self._folder_settings is not None:
            customs = self._folder_settings.load_shortcuts()

        for sc in self._shortcuts:
            sc.deleteLater()
        self._shortcuts.clear()

        _LOG.debug("apply: parent=%s actions=%d folder_settings=%s",
                    self._parent, len(actions),
                    bool(self._folder_settings))

        for name, action in actions.items():
            shortcut = customs.get(name) or DEFAULT_SHORTCUTS.get(name)
            action.setShortcut(QKeySequence())
            action.setData(shortcut or "")
            if shortcut and self._parent is not None:
                ks = QKeySequence(shortcut)
                sc = QShortcut(ks, self._parent)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                # Wrap in logging lambda to trace shortcut activation
                sc.activated.connect(
                    lambda a=action, n=name, ks_str=shortcut: self._on_activated(a, n, ks_str)
                )
                _LOG.debug("  registered %-30s %-12s on %s", name, shortcut, self._parent)
                self._shortcuts.append(sc)
            else:
                _LOG.debug("  skipped   %-30s (shortcut=%r parent=%s)", name, shortcut, self._parent)

    def _on_activated(self, action: QAction, name: str, shortcut: str) -> None:
        _LOG.debug("SHORTCUT ACTIVATED: %s (%s) → calling action.trigger()", name, shortcut)
        action.trigger()
