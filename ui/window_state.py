"""Window / session state — save and restore geometry, open tabs.

Extracted from MainWindow to reduce its size and isolate
QSettings-based persistence logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QSize

from core.logging import setup_logging

if TYPE_CHECKING:
    from ui.editor_tab import EditorTab
    from ui.settings_manager import AppSettings

_LOG = setup_logging("cutemd.window_state")


class WindowStateManager:
    """Encapsulates saving and restoring window geometry, splitter sizes,
    and the session (open folder + open tabs)."""

    def __init__(self, settings: AppSettings, tabs_widget) -> None:
        self._s = settings
        self._tabs = tabs_widget  # QTabWidget from MainWindow

    # ------------------------------------------------------------------
    # Session save / restore
    # ------------------------------------------------------------------

    def save_session(self, folder_path: Path | None) -> None:
        """Persist the list of open tab file paths and current folder."""
        tabs: list[str] = []
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if hasattr(tab, "file_path") and tab.file_path:  # EditorTab
                tabs.append(str(tab.file_path))
        self._s.set_session_restore_tabs(tabs)
        if folder_path:
            self._s.set_raw_value("session_restore_folder", str(folder_path))
        else:
            self._s.set_raw_value("session_restore_folder", "")

    def restore_session(
        self,
        set_folder_fn,
        add_tab_fn,
    ) -> bool:
        """Restore folder and open tabs from the last session.

        Returns True if any tabs were restored.
        """
        _LOG.debug("restore_session: enabled=%s", self._s.session_restore_enabled())
        if not self._s.session_restore_enabled():
            return False

        # Restore folder first if one was open.
        folder_str = self._s.raw_value("session_restore_folder", "")
        if folder_str:
            folder = Path(folder_str)
            if folder.is_dir():
                set_folder_fn(folder)

        saved_tabs = self._s.session_restore_tabs()
        _LOG.debug("restore_session: folder=%s tabs=%d", folder_str, len(saved_tabs))
        if not saved_tabs:
            return False

        restored = 0
        for path_str in saved_tabs:
            p = Path(path_str)
            if p.is_file():
                tab = add_tab_fn()
                tab.load_file(p)
                restored += 1

        if restored > 0:
            # Remove the untitled tab left by _set_folder / the initial one.
            untitled = self._tabs.widget(0)
            if hasattr(untitled, "file_path") and untitled.file_path is None:
                self._tabs.removeTab(0)

        return restored > 0

    # ------------------------------------------------------------------
    # Window geometry
    # ------------------------------------------------------------------

    def save_window_geometry(self, geometry: QByteArray) -> None:
        self._s.set_window_geometry(geometry)

    def restore_window_geometry(self) -> QByteArray | None:
        return self._s.window_geometry()

    # ------------------------------------------------------------------
    # Splitter / panel width
    # ------------------------------------------------------------------

    def save_left_panel_width(self, width: int) -> None:
        self._s.set_left_panel_width(width)
        self._s._s.sync()

    # ------------------------------------------------------------------
    # Convenience — close event actions
    # ------------------------------------------------------------------

    def on_close(
        self,
        folder_path: Path | None,
        splitter_sizes: tuple[int, int],
        window_geometry: QByteArray,
        left_splitter_sizes: list[int] | None = None,
        right_dock_sizes: list[int] | None = None,
    ) -> None:
        """Persist session, geometry, and panel state on close."""
        if self._s.session_restore_enabled():
            self.save_session(folder_path)
        self.save_window_geometry(window_geometry)
        left = splitter_sizes[0]
        _LOG.debug("on_close: left=%d", left)
        if left > 0:
            self.save_left_panel_width(left)
        if right_dock_sizes:
            _LOG.debug("on_close: right_dock_sizes=%s", right_dock_sizes)
            self._s.set_right_dock_sizes(right_dock_sizes)
        self._s._s.sync()  # always flush to disk
