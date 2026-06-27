"""Centralized QSettings access — single source of truth for all preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QSettings, Signal


class AppSettings(QObject):
    """Singleton-style wrapper around QSettings with typed accessors."""

    theme_changed = Signal(str)
    editor_font_changed = Signal(str, int)
    preview_font_changed = Signal(str, int)
    language_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._s = QSettings("cutemd", "cutemd")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def theme(self, default: str = "system") -> str:
        return str(self._s.value("theme", default))

    def set_theme(self, value: str) -> None:
        self._s.setValue("theme", value)
        self.theme_changed.emit(value)

    # ------------------------------------------------------------------
    # Editor font
    # ------------------------------------------------------------------
    def editor_font_family(self, default: str = "System") -> str:
        val = str(self._s.value("editor_font_family", default))
        return "System" if val == "Sistema" else val

    def set_editor_font_family(self, value: str) -> None:
        self._s.setValue("editor_font_family", value)

    def editor_font_size(self, default: int = 13) -> int:
        return int(self._s.value("editor_font_size", default))

    def set_editor_font_size(self, value: int) -> None:
        self._s.setValue("editor_font_size", value)

    # ------------------------------------------------------------------
    # Preview font
    # ------------------------------------------------------------------
    def preview_font_family(self, default: str = "System") -> str:
        val = str(self._s.value("preview_font_family", default))
        return "System" if val == "Sistema" else val

    def set_preview_font_family(self, value: str) -> None:
        self._s.setValue("preview_font_family", value)

    def preview_font_size(self, default: int = 13) -> int:
        return int(self._s.value("preview_font_size", default))

    def set_preview_font_size(self, value: int) -> None:
        self._s.setValue("preview_font_size", value)

    # ------------------------------------------------------------------
    # Line numbers
    # ------------------------------------------------------------------
    def line_number_mode(self, default: int = 1) -> int:
        return int(self._s.value("line_number_mode", default))

    def set_line_number_mode(self, value: int) -> None:
        self._s.setValue("line_number_mode", value)

    # ------------------------------------------------------------------
    # Cursor
    # ------------------------------------------------------------------
    def cursor_width(self, default: int = 2) -> int:
        return int(self._s.value("cursor_width", default))

    def set_cursor_width(self, value: int) -> None:
        self._s.setValue("cursor_width", value)

    # ------------------------------------------------------------------
    # Smart editing
    # ------------------------------------------------------------------
    def smart_editing(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        if default is None:
            default = {
                "auto_pair_delimiters": True,
                "auto_pair_brackets": True,
                "list_continuation": True,
                "tab_move_to_next_cell": True,
            }
        val = self._s.value("smart_editing", default)
        return val if isinstance(val, dict) else default

    def set_smart_editing(self, value: dict[str, Any]) -> None:
        self._s.setValue("smart_editing", value)

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------
    def language(self, default: str = "system") -> str:
        return str(self._s.value("language", default))

    def set_language(self, value: str) -> None:
        self._s.setValue("language", value)
        self.language_changed.emit(value)

    # ------------------------------------------------------------------
    # Folder state
    # ------------------------------------------------------------------
    def last_folder(self) -> str:
        return str(self._s.value("last_folder", ""))

    def set_last_folder(self, path: str | Path) -> None:
        self._s.setValue("last_folder", str(path))

    def remove_last_folder(self) -> None:
        self._s.remove("last_folder")

    def recent_folders(self) -> list[str]:
        val = self._s.value("recent_folders", [])
        if isinstance(val, str):
            return [val] if val else []
        return list(val) if isinstance(val, list) else []

    def set_recent_folders(self, folders: list[str]) -> None:
        self._s.setValue("recent_folders", folders)

    # ------------------------------------------------------------------
    # Window geometry
    # ------------------------------------------------------------------
    def window_geometry(self) -> Any:
        return self._s.value("window_geometry")

    def set_window_geometry(self, geometry: Any) -> None:
        self._s.setValue("window_geometry", geometry)

    # ------------------------------------------------------------------
    # Splitter
    # ------------------------------------------------------------------
    def left_panel_width(self, default: int = 220) -> int:
        return int(self._s.value("left_panel_width", default))

    def set_left_panel_width(self, width: int) -> None:
        self._s.setValue("left_panel_width", width)

    # ------------------------------------------------------------------
    # Autosave
    # ------------------------------------------------------------------
    def autosave_interval(self, default: int = 5) -> int:
        return int(self._s.value("autosave_interval", default))

    def set_autosave_interval(self, value: int) -> None:
        self._s.setValue("autosave_interval", value)

    # ------------------------------------------------------------------
    # Auto-sync
    # ------------------------------------------------------------------
    def auto_sync_enabled(self, default: bool = False) -> bool:
        val = self._s.value("auto_sync_enabled", default)
        return str(val).lower() == "true" if isinstance(val, str) else bool(val)

    def set_auto_sync_enabled(self, value: bool) -> None:
        self._s.setValue("auto_sync_enabled", value)

    def auto_sync_interval(self, default: int = 300) -> int:
        return int(self._s.value("auto_sync_interval", default))

    def set_auto_sync_interval(self, value: int) -> None:
        self._s.setValue("auto_sync_interval", value)

    def sync_on_save(self, default: bool = False) -> bool:
        val = self._s.value("sync_on_save", default)
        return str(val).lower() == "true" if isinstance(val, str) else bool(val)

    def set_sync_on_save(self, value: bool) -> None:
        self._s.setValue("sync_on_save", value)

    # ------------------------------------------------------------------
    # Auto-update
    # ------------------------------------------------------------------
    def auto_update_check(self, default: bool = True) -> bool:
        val = self._s.value("auto_update_check", default)
        return str(val).lower() == "true" if isinstance(val, str) else bool(val)

    def set_auto_update_check(self, value: bool) -> None:
        self._s.setValue("auto_update_check", value)

    def last_update_check(self) -> str:
        return str(self._s.value("last_update_check", ""))

    def set_last_update_check(self, value: str) -> None:
        self._s.setValue("last_update_check", value)

    def ignored_update_version(self) -> str:
        return str(self._s.value("ignored_update_version", ""))

    def set_ignored_update_version(self, value: str) -> None:
        self._s.setValue("ignored_update_version", value)

    # ------------------------------------------------------------------
    # Session restore
    # ------------------------------------------------------------------
    def session_restore_enabled(self, default: bool = False) -> bool:
        val = self._s.value("session_restore_enabled", default)
        return str(val).lower() == "true" if isinstance(val, str) else bool(val)

    def set_session_restore_enabled(self, value: bool) -> None:
        self._s.setValue("session_restore_enabled", value)

    def session_restore_tabs(self) -> list[str]:
        val = self._s.value("session_restore_tabs", [])
        if isinstance(val, str):
            return [val] if val else []
        return list(val) if isinstance(val, list) else []

    def set_session_restore_tabs(self, tabs: list[str]) -> None:
        self._s.setValue("session_restore_tabs", tabs)

    # ------------------------------------------------------------------
    # File tree
    # ------------------------------------------------------------------
    def show_hidden_files(self, default: bool = False) -> bool:
        val = self._s.value("show_hidden_files", default)
        return str(val).lower() == "true" if isinstance(val, str) else bool(val)

    def set_show_hidden_files(self, value: bool) -> None:
        self._s.setValue("show_hidden_files", value)

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def menu_bar_visible(self, default: bool = True) -> bool:
        val = self._s.value("menu_bar_visible", default)
        return str(val).lower() == "true" if isinstance(val, str) else bool(val)

    def set_menu_bar_visible(self, value: bool) -> None:
        self._s.setValue("menu_bar_visible", value)

    # ------------------------------------------------------------------
    # Raw access (for backward compat / complex values)
    # ------------------------------------------------------------------
    def raw_value(self, key: str, default: Any = None) -> Any:
        return self._s.value(key, default)

    def set_raw_value(self, key: str, value: Any) -> None:
        self._s.setValue(key, value)

    # ------------------------------------------------------------------
    # Config file path (display-only)
    # ------------------------------------------------------------------
    @staticmethod
    def config_file_path() -> str:
        """Return the QSettings file path for display purposes."""
        from PySide6.QtCore import QSettings
        return QSettings("cutemd", "cutemd").fileName()

    # ------------------------------------------------------------------
    # Right dock
    # ------------------------------------------------------------------
    def right_dock_visible(self, default: bool = True) -> bool:
        val = self._s.value("right_dock_visible", default)
        return str(val).lower() == "true" if isinstance(val, str) else bool(val)

    def set_right_dock_visible(self, value: bool) -> None:
        self._s.setValue("right_dock_visible", value)

    def right_dock_sizes(self, default: list[int] | None = None) -> list[int]:
        val = self._s.value("right_dock_sizes", default or [])
        return [int(x) for x in val] if isinstance(val, list) else (default or [])

    def set_right_dock_sizes(self, sizes: list[int]) -> None:
        self._s.setValue("right_dock_sizes", sizes)

    def right_dock_width(self, default: int = 200) -> int:
        return int(self._s.value("right_dock_width", default))

    def set_right_dock_width(self, width: int) -> None:
        self._s.setValue("right_dock_width", width)

    # ------------------------------------------------------------------
    # Clear last folder + recent folders
    # ------------------------------------------------------------------
    def remove_recent_folders(self) -> None:
        self._s.remove("recent_folders")
