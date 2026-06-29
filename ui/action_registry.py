"""Centralized QAction creation, menu-bar setup, and action map.

Extracted from MainWindow to reduce its size and eliminate the
three duplicated action-name → QAction mappings.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenuBar


def _tr(context: QMainWindow, text: str) -> str:
    """Short hand for context.tr()."""
    return context.tr(text)  # type: ignore[attr-defined]


class ActionRegistry:
    """Creates every QAction the application needs and wires up the menu bar.

    The registry exposes a single ``all`` dict so callers that need an
    action-name → QAction map (shortcut manager, command palette,
    shortcuts dialog) can obtain it without repeating the dict literal.
    """

    def __init__(self, window: QMainWindow) -> None:
        self._w = window
        self._acts: dict[str, QAction] = {}
        self._menus: dict[str, QMenuBar] = {}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def all(self) -> dict[str, QAction]:
        return dict(self._acts)

    def build(self, callbacks: dict[str, object]) -> None:
        """Create every QAction, connect callbacks, and build the menu bar.

        *callbacks* is a flat dict mapping action name → callable.
        """
        self._create_actions(callbacks)
        self._setup_menubar()

    # ------------------------------------------------------------------
    # Action factories
    # ------------------------------------------------------------------

    def _create_actions(self, cb: dict[str, object]) -> None:
        w = self._w
        self._acts["act_open_folder"] = self._action(
            "Open &Folder…", QKeySequence.StandardKey.Open, cb.get("open_folder")
        )
        self._acts["act_close_folder"] = self._action(
            "Close Folder", None, cb.get("close_folder")
        )
        self._acts["act_new"] = self._action(
            "&New File…", QKeySequence.StandardKey.New, cb.get("new")
        )
        self._acts["act_new_from_template"] = self._action(
            "New from &Template…", None, cb.get("new_from_template")
        )
        self._acts["act_save"] = self._action(
            "&Save", QKeySequence.StandardKey.Save, cb.get("save")
        )
        self._acts["act_save_as"] = self._action(
            "Save &As…", QKeySequence.StandardKey.SaveAs, cb.get("save_as")
        )
        self._acts["act_close_tab"] = self._action(
            "Close Tab", QKeySequence.StandardKey.Close, cb.get("close_tab")
        )
        # Exit — always close
        self._acts["act_exit"] = self._action(
            "E&xit", QKeySequence.StandardKey.Quit, w.close
        )

        # Edit
        self._acts["act_undo"] = self._action(
            "&Undo", QKeySequence.StandardKey.Undo, None
        )
        self._acts["act_redo"] = self._action(
            "&Redo", QKeySequence.StandardKey.Redo, None
        )
        self._acts["act_find"] = self._action(
            "&Find…", QKeySequence.StandardKey.Find, cb.get("find")
        )
        self._acts["act_find_files"] = self._action(
            "Find in &Files…",
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_F),
            cb.get("find_files"),
        )
        self._acts["act_replace_files"] = self._action(
            "Replace in &Files…",
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_H),
            cb.get("replace_files"),
        )

        # View
        self._acts["act_toggle_preview"] = self._action(
            "Toggle &Preview", None, None, checkable=True, checked=True
        )
        self._acts["act_toggle_split"] = self._action(
            "Toggle Split &Orientation", None, cb.get("toggle_split")
        )
        self._acts["act_toggle_tree"] = self._action(
            "Toggle &File Tree", QKeySequence("Ctrl+B"), None,
            checkable=True, checked=True,
        )
        self._acts["act_toggle_tags"] = self._action(
            "Toggle &Tags", QKeySequence("Ctrl+Shift+T"), None,
            checkable=True, checked=False,
        )
        self._acts["act_toggle_statusbar"] = self._action(
            "Toggle Status &Bar", None, None, checkable=True, checked=True
        )

        self._acts["act_settings"] = self._action(
            "&Settings…", QKeySequence("Ctrl+,"), cb.get("settings")
        )
        self._acts["act_shortcuts"] = self._action(
            "&Keyboard Shortcuts…", QKeySequence("Ctrl+/"), cb.get("shortcuts")
        )
        self._acts["act_check_update"] = self._action(
            "Check for &Updates…", None,
            lambda: (cb.get("check_update") or (lambda s=False: None))(silent=False),
        )
        self._acts["act_command_palette"] = self._action(
            "&Command Palette…", None, cb.get("command_palette")
        )
        self._acts["act_webdav_sync"] = self._action(
            "&Sync Now", QKeySequence("Ctrl+Shift+Y"), cb.get("webdav_sync")
        )

        # Zoom
        self._acts["act_zoom_in"] = self._action(
            "Zoom &In (Editor)", QKeySequence("Ctrl+="),
            lambda: (cb.get("zoom_editor") or (lambda d: None))(1),
        )
        self._acts["act_zoom_out"] = self._action(
            "Zoom &Out (Editor)", QKeySequence("Ctrl+-"),
            lambda: (cb.get("zoom_editor") or (lambda d: None))(-1),
        )
        self._acts["act_zoom_reset"] = self._action(
            "&Reset Zoom", QKeySequence("Ctrl+0"), cb.get("zoom_reset")
        )
        self._acts["act_zoom_preview_in"] = self._action(
            "Zoom Preview &In", QKeySequence("Ctrl+Shift+="),
            lambda: (cb.get("zoom_preview") or (lambda d: None))(1),
        )
        self._acts["act_zoom_preview_out"] = self._action(
            "Zoom Preview O&ut", QKeySequence("Ctrl+Shift+-"),
            lambda: (cb.get("zoom_preview") or (lambda d: None))(-1),
        )

    def _action(
        self,
        text: str,
        shortcut: QKeySequence | QKeySequence.StandardKey | None = None,
        triggered: object = None,
        *,
        checkable: bool = False,
        checked: bool = False,
    ) -> QAction:
        act = QAction(_tr(self._w, text), self._w)
        if shortcut is not None:
            act.setShortcut(shortcut)
        if checkable:
            act.setCheckable(True)
            act.setChecked(checked)
        if triggered is not None:
            act.triggered.connect(triggered)  # type: ignore[arg-type]
        return act

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _setup_menubar(self) -> None:
        mb = self._w.menuBar()

        def _menu(title: str) -> object:
            m = mb.addMenu(_tr(self._w, title))
            return m

        fm = _menu("&File")
        fm.addAction(self._acts["act_open_folder"])
        fm.addAction(self._acts["act_close_folder"])
        fm.addSeparator()
        fm.addAction(self._acts["act_new"])
        fm.addAction(self._acts["act_new_from_template"])
        fm.addAction(self._acts["act_save"])
        fm.addAction(self._acts["act_save_as"])
        fm.addSeparator()
        fm.addAction(self._acts["act_webdav_sync"])
        fm.addSeparator()
        fm.addAction(self._acts["act_close_tab"])
        fm.addSeparator()
        fm.addAction(self._acts["act_exit"])
        self._menus["file"] = fm  # type: ignore[assignment]

        em = _menu("&Edit")
        em.addAction(self._acts["act_undo"])
        em.addAction(self._acts["act_redo"])
        em.addSeparator()
        em.addAction(self._acts["act_find"])
        em.addAction(self._acts["act_find_files"])
        em.addAction(self._acts["act_replace_files"])
        self._menus["edit"] = em  # type: ignore[assignment]

        vm = _menu("&View")
        vm.addAction(self._acts["act_toggle_preview"])
        vm.addSeparator()
        vm.addAction(self._acts["act_toggle_tree"])
        vm.addAction(self._acts["act_toggle_statusbar"])
        vm.addSeparator()
        vm.addAction(self._acts["act_zoom_in"])
        vm.addAction(self._acts["act_zoom_out"])
        vm.addAction(self._acts["act_zoom_reset"])
        vm.addSeparator()
        vm.addAction(self._acts["act_zoom_preview_in"])
        vm.addAction(self._acts["act_zoom_preview_out"])
        self._menus["view"] = vm  # type: ignore[assignment]

        sm = _menu("&Settings")
        sm.addAction(self._acts["act_settings"])
        self._menus["settings"] = sm  # type: ignore[assignment]

        hm = _menu("&Help")
        hm.addAction(self._acts["act_command_palette"])
        hm.addSeparator()
        hm.addAction(self._acts["act_check_update"])
        hm.addSeparator()
        hm.addAction(self._acts["act_shortcuts"])
        self._menus["help"] = hm  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Access to individual menus (for retranslate)
    # ------------------------------------------------------------------

    def menu(self, name: str):
        return self._menus.get(name)
