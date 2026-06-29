"""Settings applicator — applies settings-dialog results to MainWindow.

Extracted from MainWindow._on_settings() to reduce its size.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication

from core.logging import setup_logging
from ui.editor_tab import EditorTab
from ui.themes import get_theme, system_theme

if TYPE_CHECKING:
    from ui.editor_tab import EditorTab
    from ui.main_window import MainWindow
    from ui.settings_dialog import SettingsDialog

_LOG = setup_logging("cutemd.settings_applicator")


class SettingsApplicator:
    """Applies the user's settings dialog choices to the running application."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    def apply(self, dlg: SettingsDialog) -> None:
        """Read every selected value from *dlg* and push it to the window."""
        w = self._w

        # --- Theme ---
        new_theme_id = dlg.selected_theme_id()
        _LOG.debug("DIAG SettingsApplicator: new_theme=%s old=%s match=%s",
                   new_theme_id, w._theme_id, new_theme_id == w._theme_id)
        if new_theme_id != w._theme_id:
            w._theme_id = new_theme_id
            w._current_theme = (
                system_theme() if new_theme_id == "system"
                else get_theme(new_theme_id)
            )
            w._apply_theme()

        # --- Language ---
        new_lang = dlg.selected_language()
        if new_lang != w._language:
            w._language = new_lang
            w._s.set_language(new_lang)
            from ui.translations import apply_language

            app = QApplication.instance()
            if isinstance(app, QApplication):
                apply_language(app, new_lang)

        # --- Fonts ---
        new_ef = dlg.selected_editor_font()
        new_efs = dlg.selected_editor_font_size()
        new_pf = dlg.selected_preview_font()
        new_pfs = dlg.selected_preview_font_size()

        changed = False
        if new_ef != w._editor_font_family or new_efs != w._editor_font_size:
            w._editor_font_family = new_ef
            w._editor_font_size = new_efs
            changed = True
        if new_pf != w._preview_font_family or new_pfs != w._preview_font_size:
            w._preview_font_family = new_pf
            w._preview_font_size = new_pfs
            changed = True
        if changed:
            for i in range(w._tabs.count()):
                tab = w._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_editor_font(w._editor_font_family, w._editor_font_size)
                    tab.set_preview_font(w._preview_font_family, w._preview_font_size)

        # --- Line numbers ---
        new_ln = dlg.selected_line_number_mode()
        if new_ln != w._line_number_mode:
            w._line_number_mode = new_ln
            for i in range(w._tabs.count()):
                tab = w._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_line_number_mode(new_ln)

        # --- Cursor width ---
        new_cw = dlg.selected_cursor_width()
        if new_cw != w._cursor_width:
            w._cursor_width = new_cw
            for i in range(w._tabs.count()):
                tab = w._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_cursor_width(new_cw)

        # --- Smart editing ---
        new_se = dlg.selected_smart_editing()
        new_ls = dlg.selected_link_style()
        new_se["link_style"] = new_ls
        if new_se != w._smart_editing:
            w._smart_editing = new_se
            for key, val in new_se.items():
                w._s.set_raw_value(f"smart_editing/{key}", val)
            w._s.set_raw_value("link_style", new_ls)
            for i in range(w._tabs.count()):
                tab = w._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_smart_editing(new_se)

        # --- Autosave interval ---
        new_asi = dlg.selected_autosave_interval()
        if new_asi != w._s.autosave_interval():
            w._s.set_autosave_interval(new_asi)
            w._autosave_interval = max(1, new_asi) * 1000
            w._autosave_timer.setInterval(w._autosave_interval)

        # --- Auto-update ---
        w._s.set_auto_update_check(dlg.selected_auto_update_check())

        # --- Session restore (global) ---
        w._s.set_session_restore_enabled(dlg.selected_session_restore_enabled())

        # --- Menu bar ---
        new_mbv = dlg.selected_menu_bar_visible()
        old_mbv = w._s.menu_bar_visible()
        _LOG.debug("apply: menu_bar new=%s old=%s", new_mbv, old_mbv)
        if new_mbv != old_mbv:
            w._s.set_menu_bar_visible(new_mbv)
            w.menuBar().setVisible(new_mbv)

        # --- Per-folder settings ---
        if w._folder_settings is not None:
            self._apply_folder_settings(dlg)

        # --- Show hidden files (global) ---
        new_shf = dlg.selected_show_hidden_files()
        if new_shf != w._show_hidden_files:
            w._show_hidden_files = new_shf
            w._s.set_show_hidden_files(new_shf)
            w._tree_panel.set_show_hidden_files(new_shf)

    # ------------------------------------------------------------------
    # Per-folder settings
    # ------------------------------------------------------------------

    def _apply_folder_settings(self, dlg: SettingsDialog) -> None:
        w = self._w
        fs = w._folder_settings
        if fs is None:
            return

        new_sc = dlg.selected_shortcuts()
        fs.save_shortcuts(new_sc)

        cfg = fs.load()
        new_id = dlg.selected_attachments_dir()
        if new_id is not None:
            # Store relative to vault root when possible.
            p = Path(new_id)
            if p.is_absolute():
                try:
                    new_id = str(p.resolve().relative_to(fs.folder))
                except (ValueError, OSError):
                    pass
            cfg["attachments_dir"] = new_id

        cfg["theme"] = w._theme_id
        cfg["editor_font_family"] = w._editor_font_family
        cfg["editor_font_size"] = w._editor_font_size
        cfg["preview_font_family"] = w._preview_font_family
        cfg["preview_font_size"] = w._preview_font_size
        cfg["line_number_mode"] = w._line_number_mode
        cfg["cursor_width"] = w._cursor_width
        fs.save(cfg)

        w._shortcut_mgr._folder_settings = fs
        w._shortcut_mgr.apply(w._all_actions)

        # Propagate updated attachments_dir to all open tabs
        attachments_dir = fs.attachments_dir()
        for i in range(w._tabs.count()):
            tw = w._tabs.widget(i)
            if isinstance(tw, EditorTab):
                tw.set_attachments_dir(attachments_dir)

        # WebDAV config
        new_url = dlg.selected_webdav_url()
        new_user = dlg.selected_webdav_username()
        new_pass = dlg.selected_webdav_password()
        new_backup = dlg.selected_webdav_backup_dir()
        if new_url or new_user or new_pass:
            fs.save_webdav_config({
                "url": new_url, "username": new_user, "password": new_pass,
                "backup_dir": new_backup,
            })
        else:
            fs.clear_webdav_config()

        # Auto-sync settings
        w._s.set_auto_sync_enabled(dlg.selected_auto_sync_enabled())
        w._s.set_auto_sync_interval(dlg.selected_auto_sync_interval())
        w._s.set_sync_on_save(dlg.selected_sync_on_save())

        # Templates directory — store relative to vault root when possible.
        tmpl = dlg.selected_templates_dir()
        if tmpl and fs is not None:
            p = Path(tmpl)
            if p.is_absolute():
                try:
                    tmpl = str(p.resolve().relative_to(fs.folder))
                except (ValueError, OSError):
                    pass
        w._s.set_templates_dir(tmpl)

        # Daily note settings
        w._s.set_daily_notes_folder(dlg.selected_daily_folder())
        w._s.set_daily_notes_template(dlg.selected_daily_template())
        w._s.set_daily_notes_date_format(dlg.selected_daily_date_format())

        # Zen mode
        w._s.set_zen_mode_max_width(dlg.selected_zen_mode_max_width())

        # TOC in preview
        w._s.set_toc_in_preview(dlg.selected_toc_in_preview())

        w._update_auto_sync_timer()
        w._update_menu_state()
