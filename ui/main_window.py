"""Main window for the Markdown editor."""

import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.animation_speed import animation_duration_ms
from core.folder_settings import FolderSettings
from core.logging import setup_logging
from core.paths import resolve_path
from core.file_utils import default_folder_config, update_recent_folders
from core.vault_scanner import VaultScanner
from core.link_resolution import resolve_link_target
from core.webdav.sync import sync_folder
from ui.qss_loader import load_qss
from ui.action_registry import ActionRegistry
from ui.window_state import WindowStateManager
from ui.zen_mode_manager import ZenModeManager
from ui.backlinks_panel import BacklinksPanel
from ui.editor_context_menu import show_editor_context_menu
from ui.icon_provider import IconProvider
from ui.editor_tab import EditorTab
from ui.editor_toolbar import EditorToolbar
from ui.file_tree_panel import FileTreePanel
from ui.search_panel import SearchPanel
from ui.settings_manager import AppSettings
from ui.settings_applicator import SettingsApplicator
from ui.shortcut_manager import ShortcutManager
from ui.tags_panel import TagsPanel
from ui.theme_manager import ThemeManager
from ui.themes import get_theme, system_theme
from ui.side_panel_manager import SidePanelManager
from ui.toc_panel import TocPanel
from ui.metadata_panel import MetadataPanel
from ui.update_dialog import UpdateAvailableDialog

# ---------------------------------------------------------------------------
# Paths (supports PyInstaller one-file bundles)
# ---------------------------------------------------------------------------
_CSS_PATH = resolve_path("ui", "preview_styles.css")

_LOG = setup_logging("cutemd.main_window")


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

def _heading_from_display(display: str, target: str) -> str:
    """Build an ``# `` heading for a newly created link target.

    Only when the display text starts with ``#`` is it treated as a
    heading reference (e.g. ``[[# Intro|some-page]]``).  Plain display
    text such as ``[[Qualcosa|una_nota]]`` is just an alias shown in the
    preview and does NOT become file content.
    """
    text = display.strip()
    if text.startswith("#"):
        return f"# {text.lstrip('#').strip()}" if text.lstrip("#").strip() else ""
    return ""


class MainWindow(QMainWindow):
    def __init__(self, files_to_open: list[Path] | None = None) -> None:
        super().__init__()
        self._folder_path: Path | None = None
        self._folder_settings: FolderSettings | None = None
        self._files_to_open = files_to_open
        self._preview_visible = True
        self._prev_tab_index = -1

        # Settings manager (centralized QSettings wrapper)
        self._s = AppSettings(self)
        _LOG.debug("__init__: settings loaded")

        # Theme
        self._theme_manager = ThemeManager(self)
        self._theme_id = self._s.theme()
        _LOG.debug("__init__: theme=%s", self._theme_id)
        self._current_theme = self._theme_manager.resolve(self._theme_id)

        # Fonts
        self._editor_font_family = self._s.editor_font_family()
        self._editor_font_size = self._s.editor_font_size(13)
        self._preview_font_family = self._s.preview_font_family("System")
        self._preview_font_size = self._s.preview_font_size(13)

        self._icon_provider = IconProvider()
        self._zen_mode_mgr = ZenModeManager(self)
        _LOG.debug(
            "__init__: editor_font=%s %d preview_font=%s %d",
            self._editor_font_family,
            self._editor_font_size,
            self._preview_font_family,
            self._preview_font_size,
        )

        # Other settings
        self._language = self._s.language()
        self._line_number_mode = self._s.line_number_mode()
        self._cursor_width = self._s.cursor_width()
        self._smart_editing = self._s.smart_editing()
        self._smart_editing["link_style"] = self._s.raw_value("link_style", "md")
        self._show_hidden_files = self._s.show_hidden_files()

        # --- Autosave timer ---
        self._autosave_timer = QTimer(self)
        self._autosave_interval = max(1, self._s.autosave_interval()) * 1000
        self._autosave_timer.setInterval(self._autosave_interval)
        self._autosave_timer.timeout.connect(self._on_autosave)
        self._autosave_timer.start()

        # --- Auto-sync timer (starts only when enabled + WebDAV configured) ---
        self._auto_sync_timer = QTimer(self)
        self._auto_sync_timer.timeout.connect(
            lambda: self._on_webdav_sync(auto_triggered=True)
        )
        self._auto_sync_interval = max(10, self._s.auto_sync_interval()) * 1000
        self._auto_sync_timer.setInterval(self._auto_sync_interval)

        # --- TOC rebuild debounce timer ---
        self._toc_timer = QTimer(self)
        self._toc_timer.setSingleShot(True)
        self._toc_timer.setInterval(300)
        self._toc_timer.timeout.connect(self._rebuild_toc)

        # --- Backlinks scan debounce timer ---
        self._backlinks_timer = QTimer(self)
        self._backlinks_timer.setSingleShot(True)
        self._backlinks_timer.setInterval(800)
        self._backlinks_timer.timeout.connect(self._do_backlinks_scan)

        # --- Tags scan debounce timer ---
        self._tags_timer = QTimer(self)
        self._tags_timer.setSingleShot(True)
        self._tags_timer.setInterval(1000)
        self._tags_timer.timeout.connect(self._do_tags_scan)

        # Shared vault scanner — one thread, one rglob, feeds tags + backlinks.
        self._vault_scanner: VaultScanner | None = None

        # Load custom CSS once
        self._preview_css = _CSS_PATH.read_text() if _CSS_PATH.exists() else ""

        # --- Markdown parser (lazily constructed on first tab) ---
        self._md: "MarkdownIt | None" = None

        # --- UI ---
        self.setWindowTitle(self.tr("CuteMD - Markdown Editor"))

        # Restore saved window geometry, or fall back to default size
        geometry = self._s.window_geometry()
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 750)

        self._setup_actions()

        self._shortcut_mgr = ShortcutManager(None, self)
        self._shortcut_mgr.apply(self._all_actions)
        _LOG.debug("__init__: shortcuts applied, %d QShortcuts registered",
                   len(self._shortcut_mgr._shortcuts))

        # Settings applicator
        self._settings_applicator = SettingsApplicator(self)

        self._setup_statusbar()
        self._setup_central()
        self._apply_theme()

        # Menu bar visibility
        self._apply_menu_bar_visibility()

        # Restore last folder (or prompt on first run)
        QTimer.singleShot(0, self._restore_last_folder)
        # Check for updates a few seconds after startup (if enabled)
        QTimer.singleShot(4000, lambda: self._check_for_updates(silent=True))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_panel_restored", False):
            self._panel_restored = True
            self._side_panel._reset_save_timer()
            # Restore right splitter sizes on first show
            if hasattr(self, "_right_splitter"):
                saved = self._s.right_dock_sizes()
                if saved and all(s > 0 for s in saved):
                    self._right_splitter.setSizes(saved)
            # Restore right panel width
            rw = self._s.right_panel_width()
            if rw > 0 and hasattr(self, "_splitter"):
                sizes = self._splitter.sizes()
                if len(sizes) >= 3:
                    total = sum(sizes)
                    left = sizes[0]
                    mid = max(total - left - rw, 100)
                    self._splitter.setSizes([left, mid, rw])
        # Enable spell checking now that the window is visible.
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab._highlighter.enable_spell()

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Save left and right panel widths when user drags the splitter."""
        if not self._side_panel._save_allowed:
            return
        sizes = self._splitter.sizes()
        left = sizes[0] if len(sizes) > 0 else 0
        right = sizes[2] if len(sizes) > 2 else 0
        if left > 0:
            self._s.set_left_panel_width(left)
        if right > 0:
            self._s.set_right_panel_width(right)

    def _on_right_dock_splitter_moved(self, pos: int, index: int) -> None:
        """Save right splitter sizes when user drags."""
        sizes = self._right_splitter.sizes()
        if sum(sizes) > 0:
            _LOG.debug("rightSplitterMoved: %s", sizes)
            self._s.set_right_dock_sizes(sizes)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Actions & Menu bar (delegated to ActionRegistry)
    # ------------------------------------------------------------------
    def _setup_actions(self) -> None:
        callbacks = {
            "open_folder": self._on_open_folder,
            "close_folder": self._on_close_folder,
            "new": self._on_new,
            "new_from_template": self._on_new_from_template,
            "daily_note": self._on_daily_note,
            "toggle_zen_mode": self._on_toggle_zen_mode,
            "save": self._on_save,
            "save_as": self._on_save_as,
            "close_tab": self._on_close_tab,
            "find": self._on_find,
            "find_files": self._on_find_in_files,
            "replace_files": self._on_replace_in_files,
            "insert_table": self._on_insert_table,
            "toggle_split": self._toggle_split,
            "toggle_tags": self._on_toggle_tags,
            "settings": self._on_settings,
            "shortcuts": self._on_show_shortcuts,
            "check_update": self._check_for_updates,
            "command_palette": self._on_command_palette,
            "webdav_sync": self._on_webdav_sync,
            "export_note": self._on_export_note,
            "zoom_editor": self._zoom_editor,
            "zoom_reset": self._zoom_reset,
            "zoom_preview": self._zoom_preview,
        }
        self._action_registry = ActionRegistry(self)
        self._action_registry.build(callbacks)

        # Convenience aliases (kept for backward compat in the rest of the class)
        self._all_actions = self._action_registry.all
        for name, action in self._all_actions.items():
            setattr(self, name, action)

        # Wire toggles that have checkable actions
        self.act_toggle_preview.toggled.connect(self._on_toggle_preview)
        self.act_toggle_tree.toggled.connect(self._on_toggle_tree)
        self.act_toggle_tags.toggled.connect(self._on_toggle_tags)
        self.act_toggle_statusbar.toggled.connect(self._on_toggle_statusbar)

    def _apply_menu_bar_visibility(self) -> None:
        v = self._s.menu_bar_visible()
        _LOG.debug("_apply_menu_bar_visibility: %s", v)
        self.menuBar().setVisible(v)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------
    def _setup_central(self) -> None:
        """Build the central widget hierarchy.

        Layout (outer to inner):
          QHBoxLayout(outer)
            └── _left_tb (QWidget, fixed 42 px) — vertical icon toolbar
            └── _splitter (QSplitter, horizontal)
                  ├── _left_stack (QStackedWidget) — tree / search / toc panels
                  └── editor_pane (QWidget)
                        ├── EditorToolbar
                        ├── QTabWidget (editor tabs)
                        └── Inline status bar (file, cursor, words)
        """
        _LOG.debug("_setup_central: building UI")
        icon_color = self._current_theme.icon_color
        self._sidebar_buttons: list[tuple[QToolButton, str]] = []

        # --- Left vertical toolbar (ALWAYS visible, separate child in splitter) ---
        self._left_tb = QWidget()
        self._left_tb.setObjectName("leftToolbar")
        self._left_tb.setFixedWidth(42)
        self._left_tb.setMinimumWidth(42)
        lt_layout = QVBoxLayout(self._left_tb)
        lt_layout.setContentsMargins(3, 8, 3, 8)
        lt_layout.setSpacing(6)

        def _side_btn(
            name: str, tip: str, checkable: bool = True, slot=None
        ) -> QToolButton:
            b = QToolButton()
            b.setIcon(self._icon_provider.make(name, icon_color))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            b.setFixedSize(36, 30)
            b.setCheckable(checkable)
            if slot:
                b.toggled.connect(slot)
            self._sidebar_buttons.append((b, name))
            return b

        self._side_tree_btn = _side_btn(
            "folder", self.tr("Toggle file tree"), slot=self._on_side_tree_toggled
        )
        lt_layout.addWidget(self._side_tree_btn)

        self._side_search_btn = _side_btn(
            "search", self.tr("Find in files"), slot=self._on_side_search_toggled
        )
        lt_layout.addWidget(self._side_search_btn)

        self._side_tags_btn = _side_btn(
            "tag", self.tr("Toggle tags"), slot=self._on_side_tags_toggled
        )
        lt_layout.addWidget(self._side_tags_btn)

        self._side_toc_btn = _side_btn(
            "toc", self.tr("Table of Contents"), slot=self._on_side_toc_toggled
        )
        # TOC toggle moved to editor toolbar; keep button object for state sync

        lt_layout.addStretch()

        self._side_folder_btn = QToolButton()
        self._side_folder_btn.setIcon(
            self._icon_provider.make("folder_switch", icon_color)
        )
        self._side_folder_btn.setToolTip(self.tr("Switch folder"))
        self._side_folder_btn.setAutoRaise(True)
        self._side_folder_btn.setIconSize(QSize(18, 18))
        self._side_folder_btn.setFixedSize(36, 30)
        self._side_folder_btn.clicked.connect(self._on_open_folder)
        self._sidebar_buttons.append((self._side_folder_btn, "folder_switch"))
        lt_layout.addWidget(self._side_folder_btn)

        # --- Right vertical toolbar ---
        self._right_tb = QWidget()
        self._right_tb.setObjectName("rightToolbar")
        self._right_tb.setFixedWidth(42)
        self._right_tb.setMinimumWidth(42)
        rt_layout = QVBoxLayout(self._right_tb)
        rt_layout.setContentsMargins(3, 8, 3, 8)
        rt_layout.setSpacing(6)

        self._right_toc_btn = _side_btn(
            "toc", self.tr("Toggle TOC"), slot=self._on_right_toc_toggled
        )
        rt_layout.addWidget(self._right_toc_btn)

        self._right_backlinks_btn = _side_btn(
            "link", self.tr("Toggle backlinks"), slot=self._on_right_backlinks_toggled
        )
        rt_layout.addWidget(self._right_backlinks_btn)

        self._right_metadata_btn = _side_btn(
            "toc", self.tr("Toggle metadata"), slot=self._on_right_metadata_toggled
        )
        rt_layout.addWidget(self._right_metadata_btn)

        rt_layout.addStretch()

        # --- File tree panel ---
        self._tree_panel = FileTreePanel()
        self._tree_panel.file_activated.connect(self._on_tree_file_activated)
        self._tree_panel.file_double_activated.connect(
            self._on_tree_file_double_activated
        )
        self._tree_panel.file_open_new_tab.connect(self._on_tree_file_new_tab)
        self._tree_panel.file_renamed.connect(self._on_tree_file_renamed)
        self._tree_panel.file_deleted.connect(self._on_tree_file_deleted)
        self._tree_panel.set_show_hidden_files(self._show_hidden_files)

        # --- Search panel ---
        self._search_panel = SearchPanel()
        self._search_panel.file_activated.connect(
            lambda path, line: self._open_file_at_line((path, line))
        )

        # --- Left stack (tree / search) ---
        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self._tree_panel)
        self._left_stack.addWidget(self._search_panel)

        # --- Tags panel (left stack, index 2) ---
        self._tags_panel = TagsPanel()
        self._tags_panel.tag_note_activated.connect(self._on_tag_note_activated)
        self._tags_panel.tags_updated.connect(self._on_tags_updated)
        self._left_stack.addWidget(self._tags_panel)

        # Wrap left stack in a vertical splitter (for future panels)
        self._left_splitter = QSplitter(Qt.Orientation.Vertical)
        self._left_splitter.addWidget(self._left_stack)
        self._left_splitter.setChildrenCollapsible(False)

        # --- TOC panel (right dock) ---
        self._toc_panel = TocPanel()
        self._toc_panel.heading_activated.connect(self._on_toc_heading_activated)

        # --- Backlinks panel (right dock) ---
        self._backlinks_panel = BacklinksPanel()
        self._backlinks_panel.backlink_activated.connect(self._on_backlink_activated)

        # --- Right splitter (vertical: TOC + backlinks + metadata) ---
        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.addWidget(self._toc_panel)
        self._right_splitter.addWidget(self._backlinks_panel)
        self._metadata_panel = MetadataPanel()
        self._right_splitter.addWidget(self._metadata_panel)
        self._right_splitter.setChildrenCollapsible(False)
        self._right_splitter.splitterMoved.connect(self._on_right_dock_splitter_moved)

        # --- Tabs ---
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Ctrl+Tab / Ctrl+Shift+Tab — QTabWidget's built-in handling only
        # works when the tab bar has focus.  Add explicit application-wide
        # shortcuts so tab switching works from the editor too.
        from PySide6.QtGui import QKeySequence, QShortcut
        self._next_tab_sc = QShortcut(QKeySequence("Ctrl+Tab"), self)
        self._next_tab_sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._next_tab_sc.activated.connect(self._on_next_tab)
        self._prev_tab_sc = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        self._prev_tab_sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._prev_tab_sc.activated.connect(self._on_prev_tab)

        # Window state manager (geometry + session persistence)
        self._window_state = WindowStateManager(self._s, self._tabs)

        # --- Editor toolbar ---
        self._editor_toolbar = EditorToolbar(
            icon_color,
            lambda name, color, size=18: self._icon_provider.make(name, color, size),
        )
        self._editor_toolbar.format_requested.connect(self._insert_md)
        self._editor_toolbar.insert_table_requested.connect(self._on_insert_table)
        self._editor_toolbar.image_requested.connect(self._on_insert_image)
        self._editor_toolbar.toggle_search.connect(self._on_toggle_search)
        self._editor_toolbar.detach_preview.connect(self._on_detach_preview)
        editor_toolbar = self._editor_toolbar

        # --- Inline status bar ---
        self._status_file = QLabel(self.tr("..."))
        self._status_sync = QLabel("")
        self._status_encoding = QLabel("")
        self._status_cursor = QLabel(self.tr("Ln 1, Col 1"))
        self._status_words = QLabel(self.tr("0 words"))
        status_widget = QWidget()
        status_widget.setObjectName("inlineStatusBar")
        sl = QHBoxLayout(status_widget)
        sl.setContentsMargins(8, 1, 8, 1)
        sl.addWidget(self._status_file, 1)
        sl.addWidget(self._status_sync)
        sl.addWidget(self._status_encoding)
        sl.addWidget(self._status_cursor)
        sl.addWidget(self._status_words)

        # --- Editor pane ---
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self._tabs)
        editor_layout.addWidget(status_widget)

        # Splitter: left | editor | right  (toolbars are outside, always visible)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._left_splitter)
        self._splitter.addWidget(editor_pane)
        self._splitter.addWidget(self._right_splitter)
        self._splitter.setSizes([220, 726, 220])
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

        # Side panel manager (centralizes toggle/anim logic)
        self._side_panel = SidePanelManager(
            self, self._splitter, self._left_stack,
            self._side_tree_btn, self._side_search_btn, self._side_toc_btn,
            self._side_tags_btn,
            right_dock=None,
        )

        # Main layout: toolbar | splitter  (no splitter handle between them)
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._left_tb)
        outer_layout.addWidget(self._splitter)
        outer_layout.addWidget(self._right_tb)

        self.setCentralWidget(outer)

        # Hide QMainWindow status bar
        self.statusBar().hide()

        # Initial: tree visible, search hidden (block signals to skip layout while not yet shown)
        self._side_tree_btn.blockSignals(True)
        self._side_tree_btn.setChecked(True)
        self._side_tree_btn.blockSignals(False)
        self._left_stack.setCurrentIndex(0)

        # Right dock initial visibility
        _rd_vis = self._s.right_dock_visible()
        self._right_splitter.setVisible(_rd_vis)
        # Right toolbar initial checked state
        self._right_toc_btn.blockSignals(True)
        self._right_toc_btn.setChecked(_rd_vis)
        self._right_toc_btn.blockSignals(False)
        self._right_backlinks_btn.blockSignals(True)
        self._right_backlinks_btn.setChecked(_rd_vis)
        self._right_backlinks_btn.blockSignals(False)
        self._right_metadata_btn.blockSignals(True)
        self._right_metadata_btn.setChecked(_rd_vis)
        self._right_metadata_btn.blockSignals(False)

        # Hide individual panels when dock starts hidden
        if not _rd_vis:
            self._toc_panel.hide()
            self._backlinks_panel.hide()
            self._metadata_panel.hide()
        self._right_backlinks_btn.blockSignals(True)
        self._right_backlinks_btn.setChecked(True)
        self._right_backlinks_btn.blockSignals(False)

        self._preview_tab: EditorTab | None = None
        _LOG.debug("_setup_central: done")
        self._add_tab()

    # ------------------------------------------------------------------
    # Search panel (embedded find-in-files)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Side panel (delegated to SidePanelManager)
    # ------------------------------------------------------------------
    def _show_left_panel(self) -> None:
        self._side_panel.show_left_panel()

    def _hide_left_panel(self) -> None:
        self._side_panel.hide_left_panel()

    def _animate_splitter_to(self, left_width: int, on_finish=None) -> None:
        self._side_panel._animate_splitter_to(left_width, on_finish)

    def _restore_panel_width(self) -> None:
        self._side_panel.restore_panel_width()

    def _is_left_panel_open(self) -> bool:
        return self._side_panel.is_left_panel_open()

    def _on_side_tree_toggled(self, checked: bool) -> None:
        self._side_panel.on_tree_toggled(checked)

    def _on_side_search_toggled(self, checked: bool) -> None:
        self._side_panel.on_search_toggled(checked)

    def _on_side_toc_toggled(self, checked: bool) -> None:
        # Kept for SidePanelManager compatibility, now unused
        pass

    def _on_right_toc_toggled(self, checked: bool) -> None:
        """Toggle TOC visibility in the right splitter."""
        if hasattr(self, "_toc_panel"):
            self._toc_panel.setVisible(checked)
            self._sync_right_dock_visibility()
            if checked:
                self._rebuild_toc()
            else:
                self._toc_timer.stop()

    def _on_right_backlinks_toggled(self, checked: bool) -> None:
        """Toggle backlinks panel visibility in the right splitter."""
        if hasattr(self, "_backlinks_panel"):
            self._backlinks_panel.setVisible(checked)
            self._sync_right_dock_visibility()

    def _on_right_metadata_toggled(self, checked: bool) -> None:
        if hasattr(self, "_metadata_panel"):
            self._metadata_panel.setVisible(checked)
            self._sync_right_dock_visibility()
            if checked:
                tab = self._current_tab()
                if tab is not None:
                    self._update_metadata(tab)

    def _update_metadata(self, tab) -> None:
        if not hasattr(self, "_metadata_panel"):
            return
        if not hasattr(tab, "_cached_text"):
            self._metadata_panel.clear()
            return
        from core.frontmatter import parse_frontmatter
        fm = parse_frontmatter(tab._cached_text)
        if fm:
            self._metadata_panel.show_metadata(fm)
        else:
            self._metadata_panel.clear()

    def _sync_right_dock_visibility(self) -> None:
        """Show right splitter if any panel button is checked, hide if all
        unchecked.  Uses button state (not widget visibility) to avoid
        deadlock when parent is hidden."""
        toc_on = self._right_toc_btn.isChecked()
        bl_on = self._right_backlinks_btn.isChecked()
        md_on = self._right_metadata_btn.isChecked()

        if hasattr(self, "_right_splitter"):
            self._right_splitter.setVisible(toc_on or bl_on or md_on)
        if hasattr(self, "_s"):
            self._s.set_right_dock_visible(toc_on or bl_on or md_on)

    def _sync_right_toolbar_buttons(self) -> None:
        """Sync button checked states with their panel visibility.
        Call AFTER the right splitter is shown (parent must be visible)."""
        if hasattr(self, "_toc_panel") and hasattr(self, "_right_toc_btn"):
            if self._toc_panel.isVisible() != self._right_toc_btn.isChecked():
                self._right_toc_btn.setChecked(self._toc_panel.isVisible())
        if hasattr(self, "_backlinks_panel") and hasattr(self, "_right_backlinks_btn"):
            if self._backlinks_panel.isVisible() != self._right_backlinks_btn.isChecked():
                self._right_backlinks_btn.setChecked(self._backlinks_panel.isVisible())
        if hasattr(self, "_metadata_panel") and hasattr(self, "_right_metadata_btn"):
            if self._metadata_panel.isVisible() != self._right_metadata_btn.isChecked():
                self._right_metadata_btn.setChecked(self._metadata_panel.isVisible())

    def _on_side_tags_toggled(self, checked: bool) -> None:
        """Toggle the tags panel in the left stack."""
        if checked:
            self._side_panel._uncheck_others(self._side_tags_btn)
            self._left_stack.setCurrentIndex(2)
            if not self._side_panel.is_left_panel_open():
                self._side_panel.show_left_panel()
        else:
            self._side_panel.hide_left_panel()

    def _rebuild_toc(self) -> None:
        """Rebuild the table of contents from the current tab's editor content."""
        tab = self._current_tab()
        if tab and not tab._is_binary_preview:
            text = tab.editor.toPlainText()
            self._toc_panel.rebuild(text)
        else:
            self._toc_panel.clear()

    def _on_toc_heading_activated(self, line: int) -> None:
        """Scroll the editor to the given heading line."""
        tab = self._current_tab()
        if tab is None:
            return
        cursor = tab.editor.textCursor()
        block = tab.editor.document().findBlockByNumber(line)
        if block.isValid():
            cursor.setPosition(block.position())
            tab.editor.setTextCursor(cursor)
            tab.editor.centerCursor()

    # ------------------------------------------------------------------
    # Backlinks
    # ------------------------------------------------------------------

    def _trigger_backlinks_scan(self, tab: EditorTab, immediate: bool = False) -> None:
        """Start (or schedule) a backlinks scan for the file in *tab*.

        *immediate* bypasses the debounce timer (used on tab switches).
        """
        if self._folder_path is None or tab.file_path is None:
            return
        if tab._is_binary_preview:
            self._backlinks_panel.clear()
            return
        self._pending_backlinks_file = tab.file_path
        if immediate:
            self._backlinks_timer.stop()
            self._do_backlinks_scan()
        else:
            self._backlinks_timer.start()

    def _do_backlinks_scan(self) -> None:
        """Execute the pending backlinks scan."""
        fp = getattr(self, "_pending_backlinks_file", None)
        if fp is None or self._folder_path is None:
            return
        _LOG.debug("_do_backlinks_scan: %s", fp.name)
        ad = self._folder_settings.attachments_dir() if self._folder_settings else None
        self._backlinks_panel.start_scan(self._folder_path, fp, ad)

    def _on_backlink_activated(self, filepath: str) -> None:
        """Open a backlinked file in a new tab."""
        p = Path(filepath)
        idx = self._find_tab_for_file(p)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
            return
        tab = self._add_tab()
        tab.load_file(p)
        self._refresh_tab_title(tab)
        self._update_window_title()

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def _trigger_tags_scan(self) -> None:
        """Schedule a debounced tags scan (called on save events)."""
        if self._folder_path is None:
            return
        self._tags_timer.start()

    def _do_tags_scan(self) -> None:
        """Execute the pending tags scan via the shared vault scanner."""
        if self._folder_path is None:
            return
        _LOG.debug("_do_tags_scan")
        self._start_vault_scan(full=False)  # incremental — uses mtime cache

    def _on_tag_note_activated(self, filepath: str) -> None:
        """Open a note from the tags panel in a new tab."""
        p = Path(filepath)
        idx = self._find_tab_for_file(p)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
            return
        tab = self._add_tab()
        tab.load_file(p)
        self._refresh_tab_title(tab)
        self._update_window_title()

    def _on_tags_updated(self, tags: list[str]) -> None:
        """Propagate updated tag list to all editor tab completers."""
        _LOG.debug("_on_tags_updated: %d tags", len(tags))
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and hasattr(tab, "_completer"):
                tab._completer.set_tag_list(tags)

    def _start_vault_scan(self, full: bool = False) -> None:
        """Start (or restart) the shared vault scanner.

        If *full* is True the mtime cache is cleared so every file is
        re-emitted.  Otherwise only files with changed mtime are emitted.
        """
        if self._folder_path is None:
            return
        if self._vault_scanner is not None and self._vault_scanner.isRunning():
            self._vault_scanner.requestInterruption()
            self._vault_scanner.wait(2000)
        self._vault_scanner = VaultScanner(self._folder_path)
        if full:
            self._vault_scanner.invalidate()
        # Wire tags panel.
        self._tags_panel.start_scan(self._vault_scanner)
        # Collect file list for completer.
        self._vault_scanner.file_found.connect(self._on_vault_file_found)
        self._vault_scanner.scan_complete.connect(self._on_vault_scan_complete)
        self._vault_scanner.start()

    def _on_vault_file_found(self, filepath: Path) -> None:
        """Collect file paths for the editor completer."""
        if not hasattr(self, '_vault_files'):
            self._vault_files: list[str] = []
        try:
            rel = filepath.relative_to(self._folder_path)  # type: ignore[arg-type]
            self._vault_files.append(str(rel.with_suffix("")))
        except ValueError:
            pass

    def _on_vault_scan_complete(self) -> None:
        """Push collected file list to all tab completers."""
        files = sorted(set(getattr(self, '_vault_files', [])))
        if files:
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, EditorTab) and hasattr(tab, "_completer"):
                    tab._completer.set_file_list(files)
        self._vault_files = []

    def _get_or_create_md(self) -> MarkdownIt:
        """Lazily construct the MarkdownIt parser on first access.

        This defers the ~25-50ms parser construction from app startup
        to the first tab creation, which happens after the window is
        shown and the event loop is running.
        """
        if self._md is not None:
            return self._md
        from markdown_it import MarkdownIt
        from mdit_py_plugins.dollarmath import dollarmath_plugin
        from mdit_py_plugins.footnote import footnote_plugin
        from markdown.math_renderers import (
            render_math_block,
            render_math_block_label,
            render_math_inline,
            render_math_inline_double,
        )
        from markdown.tools import highlight_code
        self._md = (
            MarkdownIt("commonmark", {"highlight": highlight_code})
            .enable(["table", "strikethrough"])
            .use(dollarmath_plugin)
            .use(footnote_plugin)
        )
        self._md.renderer.rules["math_inline"] = render_math_inline  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_inline_double"] = render_math_inline_double  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block"] = render_math_block  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block_label"] = render_math_block_label  # pyright: ignore[reportAttributeAccessIssue]
        _LOG.debug("markdown parser ready (lazy)")
        return self._md

    def _add_tab(self) -> EditorTab:
        md = self._get_or_create_md()
        tab = EditorTab(
            md,
            self._preview_css,
            "dark" if self._current_theme.is_dark else "light",
            editor_font_family=self._editor_font_family,
            editor_font_size=self._editor_font_size,
            preview_font_family=self._preview_font_family,
            preview_font_size=self._preview_font_size,
            smart_editing=self._smart_editing,
            cursor_width=getattr(self, "_cursor_width", 2),
        )
        # Apply theme colors so the preview matches the current palette
        # (important for tabs created after initial _apply_theme() call).
        pal = self._current_theme.build_palette()
        from PySide6.QtGui import QPalette
        tab.set_theme(
            "dark" if self._current_theme.is_dark else "light",
            self._current_theme.pygments_style,
            theme_bg=pal.color(QPalette.ColorRole.Base).name(),
            theme_fg=pal.color(QPalette.ColorRole.Text).name(),
            theme_mid=pal.color(QPalette.ColorRole.Mid).name(),
        )
        tab.set_line_number_mode(self._line_number_mode)
        tab.set_toc_in_preview(self._s.toc_in_preview())
        tab.set_spell_check_langs(self._s.spell_check_langs())
        if self._folder_path is not None:
            tab.load_custom_dict(self._folder_path)
        tab.modified_changed.connect(self._on_tab_modified)
        tab.status_changed.connect(self._on_tab_status)
        tab.title_changed.connect(lambda: self._refresh_tab_title(tab))
        tab.file_link_clicked.connect(
            lambda target, display, t=tab: self._on_file_link_clicked(t, target, display)
        )
        tab.encoding_changed.connect(self._on_tab_encoding_changed)

        # Right-click context menu on the editor
        tab.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab.editor.customContextMenuRequested.connect(self._on_editor_context_menu)

        # Sync detach button state when preview attaches/detaches
        tab.preview_detached.connect(self._editor_toolbar._detach_btn.setChecked)

        # Insert shared toolbar into this tab
        tab.insert_toolbar(self._editor_toolbar)

        # Live TOC update
        tab.editor.textChanged.connect(self._on_editor_text_changed)

        idx = self._tabs.addTab(tab, tab.display_name())
        self._tabs.setTabToolTip(idx, tab.tooltip())
        self._tabs.setCurrentIndex(idx)
        self._connect_edit_actions(tab)

        # Enable spell check on new tabs if window is already visible.
        if self.isVisible():
            tab._highlighter.enable_spell()

        # Propagate the configured images directory to every new tab.
        if self._folder_settings is not None:
            tab.set_attachments_dir(self._folder_settings.attachments_dir())

        return tab

    def _current_tab(self) -> EditorTab | None:
        return self._tabs.currentWidget()  # type: ignore[return-value]

    def _find_tab_for_file(self, path: Path) -> int:
        """Return the tab index containing *path*, or -1."""
        resolved = path.resolve()
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and tab.file_path:
                if tab.file_path.resolve() == resolved:
                    return i
        return -1

    def _refresh_tab_title(self, tab: EditorTab) -> None:
        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is tab:
                name = tab.display_name()
                self._tabs.setTabText(i, name)
                self._tabs.setTabToolTip(i, tab.tooltip())
                if tab is self._preview_tab:
                    color = QColor(self.palette().color(self.palette().ColorRole.Text))
                    color.setAlpha(140)
                    self._tabs.tabBar().setTabTextColor(i, color)
                else:
                    self._tabs.tabBar().setTabTextColor(i, QColor())
                break

    def _connect_edit_actions(self, tab: EditorTab) -> None:
        # Disconnect any previous tab's editor from window-level undo/redo
        try:
            self.act_undo.triggered.disconnect()
        except RuntimeError:
            pass
        try:
            self.act_redo.triggered.disconnect()
        except RuntimeError:
            pass
        self.act_undo.triggered.connect(tab.editor.undo)
        self.act_redo.triggered.connect(tab.editor.redo)

    def _on_next_tab(self) -> None:
        """Switch to the next tab (wrapping around)."""
        count = self._tabs.count()
        if count > 1:
            idx = (self._tabs.currentIndex() + 1) % count
            self._tabs.setCurrentIndex(idx)

    def _on_prev_tab(self) -> None:
        """Switch to the previous tab (wrapping around)."""
        count = self._tabs.count()
        if count > 1:
            idx = (self._tabs.currentIndex() - 1) % count
            self._tabs.setCurrentIndex(idx)

    def _on_tab_changed(self, index: int) -> None:
        _LOG.debug("_on_tab_changed: index=%d", index)
        # Freeze the previously active tab's preview to save GPU memory.
        if self._prev_tab_index >= 0 and self._prev_tab_index != index:
            prev_tab = self._tabs.widget(self._prev_tab_index)
            if isinstance(prev_tab, EditorTab):
                try:
                    prev_tab.freeze_preview()
                except Exception:
                    _LOG.debug("freeze_preview failed", exc_info=True)
        self._prev_tab_index = index

        tab = self._current_tab()
        if tab:
            try:
                tab.activate_preview()
            except Exception:
                _LOG.debug("activate_preview failed", exc_info=True)
            tab.highlight_if_needed()
            self._connect_edit_actions(tab)
            tab._emit_status()
            self._update_window_title()
            # Move toolbar to the newly active tab
            tab.insert_toolbar(self._editor_toolbar)
            # Sync detach button state with new tab
            self._editor_toolbar._detach_btn.setChecked(
                tab._detached_window is not None
            )
            # Rebuild TOC if the panel is visible
            if self._right_toc_btn.isChecked():
                self._rebuild_toc()
            # Trigger backlinks scan (immediate on tab switch)
            self._trigger_backlinks_scan(tab, immediate=True)
            # Update metadata panel
            self._update_metadata(tab)

    def _on_editor_text_changed(self) -> None:
        """Debounce TOC rebuild + tag rescan when editor content changes."""
        if self._right_toc_btn.isChecked():
            self._toc_timer.start()
        self._trigger_tags_scan()
        if self._right_metadata_btn.isChecked():
            tab = self._current_tab()
            if tab is not None:
                self._update_metadata(tab)

    def _on_tab_modified(self, modified: bool) -> None:
        tab = self.sender()
        if isinstance(tab, EditorTab):
            if tab is self._preview_tab and modified:
                self._preview_tab = None
            self._refresh_tab_title(tab)
        self._update_window_title()

    def _on_tab_status(self, cursor: str, words: str) -> None:
        self._status_cursor.setText(cursor)
        self._status_words.setText(words)

    def _on_tab_encoding_changed(self, encoding: str) -> None:
        self._status_encoding.setText(encoding)

    def _on_tab_close_requested(self, index: int) -> None:
        _LOG.debug("_on_tab_close_requested: index=%d", index)
        tab = self._tabs.widget(index)
        if isinstance(tab, EditorTab):
            # Re-attach preview if detached
            if tab._detached_window is not None:
                tab._attach_preview()
            if not tab.maybe_save():
                return
        if tab is self._preview_tab:
            self._preview_tab = None
        self._tabs.removeTab(index)
        if self._tabs.count() == 0:
            self._add_tab()
        self._update_window_title()

    def _on_close_tab(self) -> None:
        idx = self._tabs.currentIndex()
        if idx >= 0:
            self._on_tab_close_requested(idx)

    # ------------------------------------------------------------------
    # Editor toolbar
    # ------------------------------------------------------------------
    def _recolor_toolbar_icons(self) -> None:
        icon_color = self._current_theme.icon_color
        provider = self._icon_provider
        for button, name in getattr(self, "_sidebar_buttons", []):
            button.setIcon(provider.make(name, icon_color))
        if hasattr(self, "_editor_toolbar"):
            self._editor_toolbar.recolor(icon_color)

    def _on_find(self) -> None:
        tab = self._current_tab()
        if isinstance(tab, EditorTab):
            tab.open_find()

    def _on_toggle_search(self) -> None:
        """Toggle the find bar in the current tab."""
        tab = self._current_tab()
        if isinstance(tab, EditorTab):
            if tab.find_bar_visible():
                tab.close_find()
            else:
                tab.open_find()

    def _on_detach_preview(self) -> None:
        """Detach or re-attach the current tab's preview pane."""
        tab = self._current_tab()
        if isinstance(tab, EditorTab):
            detached = tab.detach_preview()
            self._editor_toolbar._detach_btn.setChecked(detached)

    def _on_find_in_files(self) -> None:
        _LOG.debug("_on_find_in_files")
        if self._folder_path is None:
            return
        self._side_panel.open_search_panel()

    def _on_replace_in_files(self) -> None:
        _LOG.debug("_on_replace_in_files")
        if self._folder_path is None:
            return
        self._side_panel.open_replace_panel()

    def _open_file_at_line(self, location: tuple) -> None:
        path, line_num = location
        existing = self._find_tab_for_file(path)
        if existing >= 0:
            tab = self._tabs.widget(existing)
            self._tabs.setCurrentIndex(existing)
        else:
            tab = self._current_tab()
            if tab is not None and not tab.is_modified:
                tab.load_file(path)
            else:
                tab = self._add_tab()
                tab.load_file(path)
        # Position cursor at the target line
        block = tab.editor.document().findBlockByNumber(line_num - 1)
        if block.isValid():
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            tab.editor.setTextCursor(cursor)
            tab.editor.centerCursor()
        tab.editor.setFocus()

    def _on_editor_context_menu(self, point: QPoint) -> None:
        tab = self._current_tab()
        show_editor_context_menu(
            self,
            point,
            self._current_theme.icon_color,
            lambda name, color, size=18: self._icon_provider.make(name, color, size),
            self._insert_md,
            self._on_insert_image,
            spell_checker=tab._spell_checker if tab and hasattr(tab, "_spell_checker") else None,
            on_add_to_dict=tab.add_custom_word if tab and hasattr(tab, "add_custom_word") else None,
        )
        # --- keep existing spell-check suggestions block (appends to already-shown menu) ---
        if tab is not None and hasattr(tab, "_spell_checker") and tab._spell_checker.available:
            cursor = tab.editor.cursorForPosition(point)
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            word = cursor.selectedText()
            if word and len(word) >= 3 and not tab._spell_checker.check(word):
                menu = tab.editor.findChild(QMenu) or tab.editor.createStandardContextMenu()
                if isinstance(menu, QMenu):
                    menu.addSeparator()
                    suggestions = tab._spell_checker.suggest(word)
                    if suggestions:
                        for s in suggestions[:8]:
                            action = menu.addAction(s)
                            action.triggered.connect(
                                lambda checked, w=word, sug=s, ed=tab.editor:
                                self._replace_word(ed, w, sug)
                            )
                    else:
                        menu.addAction(self.tr("(no suggestions)")).setEnabled(False)

    def _insert_md(self, syntax: str) -> None:
        """Insert or wrap Markdown formatting at the current cursor position.

        Handles: **bold**, *italic*, ~~strikethrough~~, `code`, ```fenced```,
        [links](), ![images](), and heading prefixes (##) with appropriate
        cursor positioning after insertion.

        Args:
            syntax: Formatting type ('bold', 'italic', 'strikethrough',
                    'code', 'fenced_code', 'link', 'image', 'heading').
        """
        tab = self._current_tab()
        if tab is None:
            return
        cursor = tab.editor.textCursor()

        if syntax in ("**", "*", "~~", "`"):
            sel = cursor.selectedText()
            cursor.insertText(f"{syntax}{sel}{syntax}")
            if not sel:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Left,
                    QTextCursor.MoveMode.MoveAnchor,
                    len(syntax),
                )
                tab.editor.setTextCursor(cursor)
        elif syntax == "```":
            cursor.beginEditBlock()
            prefix = "" if cursor.atBlockStart() else "\n"
            cursor.insertText(f"{prefix}```\n\n```")
            cursor.movePosition(
                QTextCursor.MoveOperation.PreviousBlock,
                QTextCursor.MoveMode.MoveAnchor,
            )
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.MoveAnchor,
            )
            cursor.endEditBlock()
            tab.editor.setTextCursor(cursor)
        elif syntax in ("[]()", "![]()"):
            cursor.insertText(syntax)
            cursor.movePosition(
                QTextCursor.MoveOperation.Left,
                QTextCursor.MoveMode.MoveAnchor,
                len(syntax) - 1,
            )
            tab.editor.setTextCursor(cursor)
        else:
            if not cursor.atBlockStart():
                cursor.movePosition(
                    QTextCursor.MoveOperation.StartOfBlock,
                    QTextCursor.MoveMode.MoveAnchor,
                )
            cursor.insertText(syntax)
        tab.editor.setFocus()

    def _on_insert_image(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Image"),
            "",
            self.tr("Images (*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp *.ico)"),
        )
        if not path:
            return

        image_path = Path(path)

        if self._folder_path is not None and self._folder_settings is not None:
            dest_dir = self._folder_settings.attachments_dir()
            dest = dest_dir / image_path.name
            import shutil

            shutil.copy2(str(image_path), str(dest))
            try:
                rel = dest.relative_to(self._folder_path)
                self._insert_md(f"![]({rel.as_posix()})")
            except ValueError:
                self._insert_md(f"![]({dest.as_posix()})")
        else:
            self._insert_md(f"![]({image_path.as_posix()})")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _setup_statusbar(self) -> None:
        pass  # inline status bar is created in _setup_central

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        _LOG.debug("DIAG _apply_theme: theme_id=%s is_dark=%s pygments=%s",
                   self._theme_id, self._current_theme.is_dark,
                   self._current_theme.pygments_style)
        from markdown.tools import set_pygments_style

        set_pygments_style(self._current_theme.pygments_style)

        pal = self._current_theme.build_palette()
        app = QApplication.instance()
        if app is not None:
            app.setPalette(pal)
            app.setStyleSheet(load_qss(pal))

        self._recolor_toolbar_icons()
        # Extract the actual background/text colors from the palette for the preview.
        from PySide6.QtGui import QPalette
        bg_color = pal.color(QPalette.ColorRole.Base).name()
        fg_color = pal.color(QPalette.ColorRole.Text).name()
        mid_color = pal.color(QPalette.ColorRole.Mid).name()
        current_tab = self._tabs.currentWidget()
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab.set_theme(
                    "dark" if self._current_theme.is_dark else "light",
                    self._current_theme.pygments_style,
                    theme_bg=bg_color,
                    theme_fg=fg_color,
                    theme_mid=mid_color,
                    defer_rehighlight=(tab is not current_tab),
                )

    def _on_settings(self) -> None:
        """Open the settings dialog and apply changes.

        Handles per-folder shortcuts/sync config vs global preferences.
        On accept, detect which settings changed and apply incrementally
        (only re-apply theme if it actually changed, etc.).
        """
        _LOG.debug("_on_settings: opening dialog")
        from ui.settings_dialog import SettingsDialog

        webdav_url = ""
        webdav_user = ""
        webdav_pass = ""
        webdav_backup = ""

        if self._folder_settings is not None:
            cfg = self._folder_settings.load_webdav_config()
            if cfg:
                webdav_url = cfg.get("url", "")
                webdav_user = cfg.get("username", "")
                webdav_pass = cfg.get("password", "")
                webdav_backup = cfg.get("backup_dir", "")

        dlg = SettingsDialog(
            self._theme_id,
            self._editor_font_family,
            self._editor_font_size,
            self._preview_font_family,
            self._preview_font_size,
            self._language,
            self._line_number_mode,
            self._cursor_width,
            self._smart_editing.get("link_style", "md"),
            self._smart_editing,
            folder_settings=self._folder_settings,
            app_settings=self._s,
            parent=self,
            current_webdav_url=webdav_url,
            current_webdav_user=webdav_user,
            current_webdav_pass=webdav_pass,
            current_autosave_interval=self._s.autosave_interval(),
            current_auto_sync_enabled=self._s.auto_sync_enabled(),
            current_auto_sync_interval=self._s.auto_sync_interval(),
            current_sync_on_save=self._s.sync_on_save(),
            current_session_restore_enabled=self._s.session_restore_enabled(),
            current_show_hidden_files=self._show_hidden_files,
            current_webdav_backup_dir=webdav_backup,
            current_templates_dir=self._s.templates_dir(),
            current_folder=str(self._folder_settings.folder)
            if self._folder_settings is not None else "",
            current_daily_folder=self._s.daily_notes_folder(),
            current_daily_template=self._s.daily_notes_template(),
            current_daily_date_format=self._s.daily_notes_date_format(),
            current_zen_mode_max_width=self._s.zen_mode_max_width(),
            current_toc_in_preview=self._s.toc_in_preview(),
            current_spell_check_lang=self._s.spell_check_langs_str(),
            current_trash_enabled=self._s.trash_enabled(),
            current_history_enabled=self._s.history_enabled(),
            current_history_max_snapshots=self._s.history_max_snapshots(),
        )
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return

        _LOG.debug("_on_settings: applying changes")

        self._settings_applicator.apply(dlg)

        # Propagate TOC preview setting to all open tabs
        toc_enabled = self._s.toc_in_preview()
        spell_langs = self._s.spell_check_langs()
        for i in range(self._tabs.count()):
            t = self._tabs.widget(i)
            if isinstance(t, EditorTab):
                t.set_toc_in_preview(toc_enabled)
                t.set_spell_check_langs(spell_langs)

        # Global-only settings (when no folder is open)
        if self._folder_settings is None:
            self._s.set_theme(self._theme_id)
            self._s.set_editor_font_family(self._editor_font_family)
            self._s.set_editor_font_size(self._editor_font_size)
            self._s.set_preview_font_family(self._preview_font_family)
            self._s.set_preview_font_size(self._preview_font_size)
            self._s.set_line_number_mode(self._line_number_mode)
            self._s.set_cursor_width(self._cursor_width)

    
    def _update_auto_sync_timer(self) -> None:
        """Start or stop the auto-sync timer based on current settings."""
        has_webdav = (
            self._folder_settings is not None
            and self._folder_settings.has_webdav_config()
        )
        if self._s.auto_sync_enabled() and has_webdav:
            interval = max(10, self._s.auto_sync_interval()) * 1000
            self._auto_sync_timer.setInterval(interval)
            self._auto_sync_timer.start()
        else:
            self._auto_sync_timer.stop()

    def _on_toggle_preview(self, checked: bool) -> None:
        self._preview_visible = checked
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab.set_preview_visible(checked)
        # In Zen mode, double the editor width when preview is visible.
        if self._zen_mode_mgr.is_active:
            max_w = self._s.zen_mode_max_width()
            if checked:
                max_w = max_w * 2
            self._tabs.setMaximumWidth(max_w)
            ep = self._splitter.widget(1)
            if ep:
                total = self._splitter.width()
                margin = max(0, (total - max_w) // 2)
                ep.layout().setContentsMargins(margin, 0, margin, 0)

    def _save_history_snapshot(self, file_path: Path) -> None:
        if not self._s.history_enabled() or self._folder_path is None:
            return
        from core.file_history import cleanup_snapshots, save_snapshot

        save_snapshot(file_path, self._folder_path)
        cleanup_snapshots(
            file_path, self._folder_path, self._s.history_max_snapshots()
        )

    def _on_export_note(self, fmt: str) -> None:
        """Export the current note to *fmt* (html/pdf/odt/docx) via pandoc."""
        tab = self._current_tab()
        if tab is None or tab.file_path is None:
            QMessageBox.warning(self, self.tr("Export"), self.tr("No file to export."))
            return

        from core.exporter import export, pandoc_available, export_formats

        if not pandoc_available():
            QMessageBox.critical(
                self,
                self.tr("pandoc not found"),
                self.tr(
                    "pandoc is required to export notes.\n\n"
                    "Install it with your package manager:\n"
                    "  • Ubuntu/Debian: sudo apt install pandoc\n"
                    "  • macOS: brew install pandoc\n"
                    "  • Windows: winget install pandoc\n"
                    "  • Or download from https://pandoc.org"
                ),
            )
            return

        fmts = export_formats()
        if fmt not in fmts:
            return
        cfg = fmts[fmt]

        # Ensure the editor content is saved before exporting
        if tab.maybe_save() is False:
            return  # user cancelled

        from PySide6.QtWidgets import QFileDialog
        stem = tab.file_path.stem
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export as {}").format(cfg["label"]),
            str(tab.file_path.parent / stem) + cfg["ext"],
            f"{cfg['label']} (*{cfg['ext']});;All Files (*)",
        )
        if not out_path:
            return

        # For HTML, embed the current preview CSS so it matches the theme
        css = None
        if fmt == "html":
            css = self._preview_css

        try:
            export(tab.file_path, Path(out_path), fmt, css=css)
            QMessageBox.information(
                self,
                self.tr("Export"),
                self.tr("Exported to {}").format(out_path),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Export failed"),
                str(e),
            )

    def _resolve_conflicts(self, result, folder_path, folder_settings) -> None:
        """Show conflict resolution dialogs for each conflicted file."""
        from ui.conflict_resolver import (
            BinaryConflictDialog,
            MarkdownConflictDialog,
            is_binary_file,
        )
        from core.webdav.sync import (
            WebDAVClient,
            _set_file_mtime,
            _load_sync_state,
            _save_sync_state,
        )

        if folder_settings is None:
            return
        cfg = folder_settings.load_webdav_config()
        if not cfg:
            return

        client = WebDAVClient(cfg["url"], cfg["username"], cfg["password"])

        for conflict in result.conflicts:
            rel = conflict.rel_path
            local_file = folder_path / rel

            # Fetch remote text content for diff (if needed)
            if not is_binary_file(rel) and conflict.remote_text is None:
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False) as tf:
                        tmp_path = Path(tf.name)
                    if client.download(rel, tmp_path):
                        conflict.remote_text = tmp_path.read_text(encoding="utf-8")
                    tmp_path.unlink(missing_ok=True)
                except (OSError, UnicodeDecodeError) as e:
                    _LOG.debug("Failed to fetch remote text for %s: %s", rel, e)

            if is_binary_file(rel) or conflict.local_text is None or conflict.remote_text is None:
                dlg = BinaryConflictDialog(
                    rel,
                    conflict.local_size,
                    conflict.local_mtime_str,
                    conflict.remote_size,
                    conflict.remote_mtime_str,
                    self,
                )
            else:
                dlg = MarkdownConflictDialog(
                    rel,
                    conflict.local_text or "",
                    conflict.remote_text or "",
                    self,
                )

            if dlg.exec() == dlg.DialogCode.Rejected:
                continue

            action = dlg.action
            _LOG.debug("Conflict resolved: %s -> %s", rel, action)

            if action == "keep_local":
                if client.upload(local_file, rel):
                    _LOG.debug("Uploaded local version: %s", rel)
            elif action == "take_remote":
                if local_file.exists():
                    local_file.unlink()
                local_file.parent.mkdir(parents=True, exist_ok=True)
                if client.download(rel, local_file):
                    _LOG.debug("Downloaded remote version: %s", rel)
            elif action == "merged":
                merged = getattr(dlg, "merged_content", None)
                if merged:
                    local_file.write_text(merged, encoding="utf-8")
                    if client.upload(local_file, rel):
                        _LOG.debug("Uploaded merged version: %s", rel)
            # else "skip" — do nothing

            # Update sync state with new mtime
            if local_file.exists():
                state = _load_sync_state(folder_path)
                state[rel] = local_file.stat().st_mtime_ns
                _save_sync_state(folder_path, state)

    def _on_webdav_sync(self, auto_triggered: bool = False) -> None:
        """Run WebDAV sync in a background thread with progress feedback.

        Show a progress dialog while syncing. On completion, display a
        summary (files up/down/deleted/conflicts). On error, show a
        popup with the error details.
        """
        if self._folder_settings is None or self._folder_path is None:
            return

        # Prevent concurrent syncs
        if getattr(self, "_sync_busy", False):
            return

        cfg = self._folder_settings.load_webdav_config()
        if not cfg:
            if not auto_triggered:
                QMessageBox.information(
                    self,
                    self.tr("Sync"),
                    self.tr(
                        "No WebDAV configuration found for this folder.\n"
                        "Set it up in Settings \u2192 Sync."
                    ),
                )
            return

        webdav_url = cfg.get("url", "")
        user = cfg.get("username", "")
        pwd = cfg.get("password", "")
        backup_dir = cfg.get("backup_dir", "")

        from core.webdav.sync import SyncResult
        from ui.webdav_sync import BackupThread, SyncThread

        if not webdav_url:
            if not auto_triggered:
                QMessageBox.warning(
                    self, self.tr("Sync"), self.tr("WebDAV URL is not configured.")
                )
            return

        self._sync_busy = True
        self._status_sync.setText(self.tr("Syncing..."))

        # Backup is mandatory — block sync if not configured
        if not backup_dir:
            if not auto_triggered:
                QMessageBox.warning(
                    self,
                    self.tr("Sync"),
                    self.tr(
                        "No backup directory configured.\n"
                        "Set it in Settings \u2192 Sync before syncing."
                    ),
                )
            else:
                self._status_sync.setText(self.tr("Backup dir not configured"))
            return

        backup_dir_path = Path(backup_dir)
        if not backup_dir_path.is_dir():
            if not auto_triggered:
                QMessageBox.warning(
                    self,
                    self.tr("Sync"),
                    self.tr("Backup directory not found:\n{}").format(backup_dir),
                )
            else:
                self._status_sync.setText(
                    self.tr("Backup dir not found: {}").format(backup_dir)
                )
            return

        self._status_sync.setText(self.tr("Backing up..."))
        self._backup_thread = BackupThread(self._folder_path, backup_dir)

        def _on_backup_done(result_path):
            if result_path is None:
                self._sync_busy = False
                self._status_sync.setText(self.tr("Backup failed"))
                return
            self._status_sync.setText(self.tr("Syncing..."))
            self._start_webdav_sync(webdav_url, user, pwd, auto_triggered)

        def _on_backup_progress(msg):
            self._status_sync.setText(self.tr("Backup: {}").format(msg))

        self._backup_thread.progress.connect(_on_backup_progress)
        self._backup_thread.finished.connect(_on_backup_done)
        self._backup_thread.start()

    def _start_webdav_sync(
        self, url: str, user: str, pwd: str, auto_triggered: bool = False
    ) -> None:
        """Launch the WebDAV sync thread."""
        from ui.webdav_sync import SyncThread
        self._sync_thread = SyncThread(self._folder_path, url, user, pwd)

        def _on_progress(msg: str) -> None:
            self._status_sync.setText(self.tr("Sync: {}").format(msg))

        def _on_finished(result) -> None:
            self._sync_busy = False
            r: SyncResult = result

            # Build a concise status bar summary
            parts = []
            if r.uploaded:
                parts.append(self.tr("{} uploaded").format(len(r.uploaded)))
            if r.downloaded:
                parts.append(self.tr("{} downloaded").format(len(r.downloaded)))
            if r.deleted:
                parts.append(self.tr("{} deleted").format(len(r.deleted)))
            if r.unchanged:
                parts.append(self.tr("{} unchanged").format(len(r.unchanged)))
            if r.conflicts_skipped:
                parts.append(
                    self.tr("{} conflicts skipped").format(len(r.conflicts_skipped))
                )
            status = ", ".join(parts) if parts else self.tr("Sync completed")

            # Handle conflicts interactively
            if r.conflicts:
                self._resolve_conflicts(r, self._folder_path, self._folder_settings)
                # Refresh tree after resolution
                self._tree_panel.set_root_path(self._folder_path)
            if r.errors:
                status += " \u2014 " + self.tr("{} errors").format(len(r.errors))
                # Popup only on errors
                summary = self.tr("Sync completed with errors")
                if r.errors:
                    summary += "\n\n" + "\n".join(r.errors[:5])
                    if len(r.errors) > 5:
                        summary += self.tr("\n...and {} more").format(len(r.errors) - 5)
                QMessageBox.warning(self, self.tr("Sync Result"), summary)

            self._status_sync.setText(status)
            self._tree_panel.set_root_path(self._folder_path)

        self._sync_thread.progress.connect(_on_progress)
        self._sync_thread.finished.connect(_on_finished)
        self._sync_thread.start()

    def _on_show_shortcuts(self) -> None:
        from ui.shortcuts_dialog import ShortcutsDialog

        dlg = ShortcutsDialog(self._all_actions, self)
        dlg.exec()

    def _on_command_palette(self) -> None:
        _LOG.debug("_on_command_palette called")
        from ui.command_palette import CommandPalette

        dlg = CommandPalette(self._all_actions, self)
        dlg.exec()

    def _check_for_updates(self, silent: bool = False) -> None:
        """Check GitHub for a newer release (runs in background thread).

        If *silent* is True only a notification dialog is shown when an
        update is actually available.  Non-silent (menu action) also
        shows a "you're up to date" message.
        """
        from datetime import date

        today = date.today().isoformat()
        if silent:
            last = self._s.last_update_check()
            if last == today:
                return
            if not self._s.auto_update_check():
                return

        self._s.set_last_update_check(today)

        from ui.update_dialog import _CheckUpdateThread

        self._update_thread = _CheckUpdateThread(__import__("main").__version__, self)
        self._update_thread.result.connect(
            lambda info: self._on_update_check_result(info, silent)
        )
        self._update_thread.start()

    def _on_update_check_result(self, info, silent: bool) -> None:

        if info is None:
            if not silent:
                QMessageBox.information(
                    self,
                    self.tr("No Update"),
                    self.tr("You are already running the latest version."),
                )
            return

        # Check if the user skipped this version
        if silent and info.latest_tag == self._s.ignored_update_version():
            return

        dlg = UpdateAvailableDialog(info, self)
        result = dlg.exec()

        if dlg.ignore_version():
            self._s.set_ignored_update_version(info.latest_tag)

        if result != QDialog.DialogCode.Accepted:
            return

        path = dlg.downloaded_path()
        if path is None:
            return

        if info.platform_key == "windows":
            ret = QMessageBox.question(
                self,
                self.tr("Install Update"),
                self.tr(
                    "The installer has been downloaded to:\n{}\n\n"
                    "Start the installer now? The application will close."
                ).format(str(path)),
            )
            if ret == QMessageBox.StandardButton.Yes:
                import subprocess
                subprocess.Popen([str(path)])
                self.close()
        else:
            QMessageBox.information(
                self,
                self.tr("Download Complete"),
                self.tr(
                    "The file has been saved to:\n{}\n\n"
                    "You can run it or install it at your convenience."
                ).format(str(path)),
            )

    def _on_toggle_tree(self, visible: bool) -> None:
        self._side_panel.on_tree_action(visible)

    def _on_toggle_tags(self, visible: bool) -> None:
        """Handle the act_toggle_tags action (from menu / shortcut)."""
        if visible:
            self._side_panel._uncheck_others(self._side_tags_btn)
            self._left_stack.setCurrentIndex(2)
            self._side_panel.show_left_panel()
        else:
            self._side_tags_btn.setChecked(False)
            # Only hide left panel if tags was the active one
            if self._left_stack.currentIndex() == 2:
                self._side_panel.hide_left_panel()

    def _on_toggle_statusbar(self, visible: bool) -> None:
        self._status_file.parent().setVisible(visible)

    # ------------------------------------------------------------------
    # Split orientation
    # ------------------------------------------------------------------
    def _toggle_split(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        lt = tab.layout()
        if lt is None:
            return
        splitter = lt.itemAt(0)
        if splitter is None:
            return
        w = splitter.widget()
        if isinstance(w, QSplitter):
            cur = w.orientation()
            w.setOrientation(
                Qt.Orientation.Vertical
                if cur == Qt.Orientation.Horizontal
                else Qt.Orientation.Horizontal
            )

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    def _zoom_editor(self, delta: int) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        tab.zoom_editor(delta)
        self._editor_font_size = tab.editor_font_size()

    def _zoom_preview(self, delta: int) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        tab.zoom_preview(delta)
        self._preview_font_size = tab.preview_font_size()

    def _zoom_reset(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        tab.set_editor_font(self._editor_font_family, self._editor_font_size)
        tab.set_preview_font(self._preview_font_family, self._preview_font_size)

    # ------------------------------------------------------------------
    def _on_insert_table(self) -> None:
        """Open the insert-table dimensions dialog on the current tab."""
        tab = self._current_tab()
        if tab is not None:
            tab.insert_table_dialog()

    # File operations
    # ------------------------------------------------------------------
    def _on_open_folder(self) -> None:
        tab = self._current_tab()
        if tab and not tab.maybe_save():
            return

        from ui.welcome_dialog import WelcomeDialog

        dlg = WelcomeDialog(self)
        dlg.setWindowTitle(self.tr("Open Folder"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        folder = dlg.selected_folder()
        if folder is not None:
            self._set_folder(folder)

    def _set_folder(self, path: Path) -> None:
        """Open a folder: load per-folder settings, seed global defaults if needed, apply overrides.

        The order is important: theme/font overrides from the per-folder
        settings are applied *before* the UI is populated, so the user sees
        the correct appearance immediately.
        """
        self._folder_path = path
        _LOG.debug("_set_folder: %s", path)
        self._folder_settings = FolderSettings(path)
        # Seed with global defaults if .cutemd/settings.json doesn't exist yet
        if not self._folder_settings.config_path.is_file():
            global_cfg = default_folder_config(
                global_theme=self._s.theme(),
                editor_font_family=self._editor_font_family,
                editor_font_size=self._editor_font_size,
                preview_font_family=self._preview_font_family,
                preview_font_size=self._preview_font_size,
            )
            self._folder_settings.save(global_cfg)
        self._folder_settings.load()

        # Apply per-folder settings (fall back to global)
        fs = self._folder_settings
        _LOG.debug("_set_folder: settings loaded, theme=%s", fs.get_theme())
        folder_theme = fs.get_theme()
        if folder_theme is not None and folder_theme != self._theme_id:
            self._current_theme = (
                system_theme() if folder_theme == "system" else get_theme(folder_theme)
            )
            self._theme_id = folder_theme
            self._apply_theme()
        self._editor_font_family = (
            fs.get_editor_font_family() or self._editor_font_family
        )
        ef_size = fs.get_editor_font_size()
        if ef_size is not None:
            self._editor_font_size = ef_size
        self._preview_font_family = (
            fs.get_preview_font_family() or self._preview_font_family
        )
        pf_size = fs.get_preview_font_size()
        if pf_size is not None:
            self._preview_font_size = pf_size

        self._shortcut_mgr._folder_settings = self._folder_settings
        self._shortcut_mgr.apply(self._all_actions)
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._search_panel.set_folder(path)
        self._add_recent_folder(path)
        self._s.set_last_folder(path)
        self._update_auto_sync_timer()
        self._update_menu_state()
        # Defer tree+tags population by 2s so the editor is usable first.
        QTimer.singleShot(2000, lambda: self._defer_folder_population(path))

    def _defer_folder_population(self, path: Path) -> None:
        self._tree_panel.set_root_path(path)
        self._tree_panel.set_trash_config(
            self._s.trash_enabled(), self._folder_path
        )
        self._start_vault_scan(full=True)

    def _restore_last_folder(self) -> None:
        """Decide what to show on startup (called via QTimer.singleShot(0)).

        Priority order:
          1. CLI file arguments (``--path/to/file.md``) → open in edit mode
          2. Session restore (if enabled) → restore folder + open tabs
          3. Last used folder → open file tree
          4. Welcome dialog → let user pick a folder or start blank
        """
        if self._files_to_open:
            for fp in self._files_to_open:
                tab = self._current_tab()
                if tab is not None and tab.file_path is None and not tab.is_modified:
                    tab.load_file(fp)
                    self._refresh_tab_title(tab)
                else:
                    tab = self._add_tab()
                    tab.load_file(fp)
            self._update_menu_state()
            return

        # Try session restore first (if enabled and no CLI files)
        if self._window_state.restore_session(
            set_folder_fn=self._set_folder,
            add_tab_fn=self._add_tab,
        ):
            self._update_menu_state()
            return

        last = self._s.last_folder()
        if last and Path(last).is_dir():
            _LOG.debug("_restore_last_folder: last_folder=%s", last)
            self._set_folder(Path(last))
            return

        _LOG.debug("_restore_last_folder: showing welcome dialog")
        from ui.welcome_dialog import WelcomeDialog

        dlg = WelcomeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self._update_menu_state()
            return
        folder = dlg.selected_folder()
        if folder is not None:
            self._set_folder(folder)
        else:
            self._update_menu_state()

    def _update_menu_state(self) -> None:
        folder_mode = self._folder_path is not None
        self.act_close_folder.setVisible(folder_mode)
        self.act_close_folder.setEnabled(folder_mode)
        self.act_find_files.setVisible(folder_mode)
        self.act_find_files.setEnabled(folder_mode)
        self.act_replace_files.setVisible(folder_mode)
        self.act_replace_files.setEnabled(folder_mode)
        webdav_ready = (
            folder_mode
            and self._folder_settings is not None
            and self._folder_settings.has_webdav_config()
        )
        self.act_webdav_sync.setVisible(webdav_ready)
        self.act_webdav_sync.setEnabled(webdav_ready)
        has_file = self._current_tab() is not None and self._current_tab().file_path is not None
        self.act_export_html.setEnabled(has_file)
        self.act_export_pdf.setEnabled(has_file)
        self.act_export_odt.setEnabled(has_file)
        self.act_export_docx.setEnabled(has_file)
        if not folder_mode:
            self._side_panel.hide_all_panels()
            self._left_tb.hide()
            self._right_tb.hide()
            self.act_toggle_tree.setChecked(False)
            self._side_folder_btn.setText("...")
        else:
            self._side_panel.on_tree_action(True)
            self._left_tb.show()
            self._right_tb.show()
            self.act_toggle_tree.setChecked(True)
            QTimer.singleShot(0, self._restore_panel_width)
            self._side_folder_btn.setText(self._folder_path.name)
        self._update_window_title()

    def _add_recent_folder(self, path: Path) -> None:
        recent = self._s.recent_folders()
        self._s.set_recent_folders(update_recent_folders(recent, str(path.resolve())))

    def _save_session(self) -> None:
        """Save the list of open tab file paths and current folder to settings."""
        self._window_state.save_session(self._folder_path)

    def _restore_session(self) -> bool:
        """Restore folder and open tabs from the last session."""
        return self._window_state.restore_session(
            set_folder_fn=self._set_folder,
            add_tab_fn=self._add_tab,
        )

    def _on_close_folder(self) -> None:
        tab = self._current_tab()
        if tab and not tab.maybe_save():
            return
        self._folder_path = None
        self._folder_settings = None
        self._shortcut_mgr._folder_settings = None
        self._shortcut_mgr.apply(self._all_actions)
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._tree_panel.set_root_path("")
        self._search_panel.set_folder(None)
        self._backlinks_panel.clear()
        self._tags_panel.clear()
        self._tags_timer.stop()
        self._s.remove_last_folder()
        self._auto_sync_timer.stop()
        self._update_menu_state()

    def _on_tree_file_activated(self, path: str) -> None:
        """Single-click on tree: open in a preview tab."""
        _LOG.debug("_on_tree_file_activated: %s", path)
        p = Path(path)

        # Already open in some tab → focus it; if it's the preview tab, promote it.
        idx = self._find_tab_for_file(p)
        if idx >= 0:
            tab = self._tabs.widget(idx)
            if tab is self._preview_tab:
                self._preview_tab = None
                self._refresh_tab_title(tab)
            self._tabs.setCurrentIndex(idx)
            self._tree_panel.select_file(p)
            return

        # Reuse existing preview tab (if unmodified), or create a new preview tab
        if self._preview_tab is not None and not self._preview_tab.is_modified:
            tab = self._preview_tab
            self._preview_tab = None  # prevent premature promotion during load_file
            tab.load_file(p)
            self._preview_tab = tab
            self._tabs.setCurrentIndex(self._tabs.indexOf(tab))
            self._refresh_tab_title(tab)
            self._update_window_title()
            self._tree_panel.select_file(p)
            return

        # Replace an untitled, unmodified tab instead of creating a new one.
        tab = self._current_tab()
        if tab is not None and tab.file_path is None and not tab.is_modified:
            tab.load_file(p)
            self._preview_tab = tab
            self._refresh_tab_title(tab)
            self._update_window_title()
            self._tree_panel.select_file(p)
            return

        tab = self._add_tab()
        tab.load_file(p)
        self._preview_tab = tab
        self._refresh_tab_title(tab)
        self._update_window_title()
        self._tree_panel.select_file(p)

    def _on_tree_file_double_activated(self, path: str) -> None:
        """Double-click on tree: open as a persistent tab (not preview)."""
        _LOG.debug("_on_tree_file_double_activated: %s", path)
        p = Path(path)

        idx = self._find_tab_for_file(p)
        if idx >= 0:
            tab = self._tabs.widget(idx)
            if tab is self._preview_tab:
                self._preview_tab = None
                self._refresh_tab_title(tab)
            self._tabs.setCurrentIndex(idx)
            self._tree_panel.select_file(p)
            return

        # If the current tab is the preview tab → promote and reuse it
        tab = self._current_tab()
        if tab is self._preview_tab:
            self._preview_tab = None
            tab.load_file(p)
            self._refresh_tab_title(tab)
            self._update_window_title()
            self._tree_panel.select_file(p)
            return

        # Replace an untitled, unmodified tab instead of creating a new one.
        if tab is not None and tab.file_path is None and not tab.is_modified:
            tab.load_file(p)
            self._refresh_tab_title(tab)
            self._update_window_title()
            self._tree_panel.select_file(p)
            return

        # Otherwise open in a new persistent tab
        tab = self._add_tab()
        tab.load_file(p)
        self._refresh_tab_title(tab)
        self._update_window_title()
        self._tree_panel.select_file(p)

    def _on_tree_file_new_tab(self, path: str) -> None:
        """Open *path* in a new tab, or focus existing tab if already open."""
        p = Path(path)
        idx = self._find_tab_for_file(p)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
            return
        tab = self._add_tab()
        tab.load_file(p)
        self._refresh_tab_title(tab)
        self._update_window_title()
        self._tree_panel.select_file(p)

    def _on_tree_file_renamed(self, old_path: str, new_path: str) -> None:
        """Update any open tab pointing to the old path."""
        old = Path(old_path).resolve()
        new = Path(new_path).resolve()
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and tab.file_path:
                if tab.file_path.resolve() == old:
                    tab._file_path = new
                    self._refresh_tab_title(tab)
                    self._tree_panel.select_file(new)
                elif old in tab.file_path.resolve().parents:
                    tab._file_path = new / tab.file_path.resolve().relative_to(old)
                    self._refresh_tab_title(tab)
        self._update_window_title()

    def _on_tree_file_deleted(self, path: str) -> None:
        """Close any open tab pointing to the deleted path."""
        deleted = Path(path).resolve()
        to_close = []
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and tab.file_path:
                resolved = tab.file_path.resolve()
                if resolved == deleted or deleted in resolved.parents:
                    to_close.append(i)
        for i in reversed(to_close):
            self._on_tab_close_requested(i)

    def _on_file_link_clicked(
        self, source_tab: EditorTab, target: str, display: str = ""
    ) -> None:
        """Click on a link/wikilink — open URL in browser or file in a tab.

        If the target markdown file does not exist and a folder is open,
        create it (with an optional heading derived from the display text).
        """
        # URLs → open in browser
        if target.startswith(("http://", "https://", "www.")):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            url = target if "://" in target else "https://" + target
            QDesktopServices.openUrl(QUrl(url))
            return

        source_dir = source_tab.file_path.parent if source_tab.file_path else (
            self._folder_path if self._folder_path else Path.cwd()
        )
        attachments_dir = (
            self._folder_settings.attachments_dir()
            if self._folder_settings is not None
            else None
        )
        path = resolve_link_target(target, source_dir, attachments_dir)

        # File not found → create it (only in folder mode).
        if path is None:
            if self._folder_path is None:
                return
            path = self._folder_path / (target + ".md")
            # Avoid overwriting an existing file (race condition).
            if not path.exists():
                heading = _heading_from_display(display, target)
                path.write_text(f"{heading}\n", encoding="utf-8")
                _LOG.debug("created missing link target: %s", path)

        idx = self._find_tab_for_file(path)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
            return

        tab = self._add_tab()
        tab.load_file(path)
        self._refresh_tab_title(tab)
        self._update_window_title()

    def _on_autosave(self) -> None:
        """Autosave: silently save all modified tabs with a file path."""
        _LOG.debug("_on_autosave: triggering")
        saved_any = False
        saved_tab = None
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                if tab.auto_save() is not False:
                    saved_any = True
                    saved_tab = tab
                    if tab.file_path:
                        self._save_history_snapshot(tab.file_path)
        if saved_any and self._s.sync_on_save():
            self._on_webdav_sync(auto_triggered=True)
        if saved_any:
            self._trigger_tags_scan()
            if saved_tab is not None:
                self._update_metadata(saved_tab)

    def _on_toggle_zen_mode(self, enabled: bool) -> None:
        """Enter / leave zen mode: hide all chrome, center the editor."""
        self._zen_mode_mgr.toggle(enabled)

    def _on_new(self) -> None:
        tab = self._current_tab()
        if tab is not None and tab.file_path is None and not tab.is_modified:
            self._tabs.setCurrentIndex(self._tabs.indexOf(tab))
            return
        self._add_tab()
        self._update_window_title()

    def _on_new_from_template(self) -> None:
        from ui.template_picker import TemplatePicker

        tmpl_dir_str = self._s.templates_dir()
        if tmpl_dir_str and self._folder_settings is not None:
            p = Path(tmpl_dir_str)
            if not p.is_absolute():
                tmpl_dir_str = str(self._folder_settings.folder / p)
        tmpl_dir = Path(tmpl_dir_str) if tmpl_dir_str else None

        dlg = TemplatePicker(tmpl_dir, self)
        if dlg.exec() != TemplatePicker.DialogCode.Accepted:
            return

        tab = self._add_tab()
        self._update_window_title()

        content = TemplatePicker.resolve_content(dlg.selected_path)
        if content:
            tab.editor.setPlainText(content)
            tab.editor.document().setModified(False)

    def _on_daily_note(self) -> None:
        if self._folder_settings is None:
            return

        from datetime import date
        from ui.template_picker import TemplatePicker

        fmt = self._s.daily_notes_date_format()
        folder_name = self._s.daily_notes_folder()
        today_str = date.today().strftime(fmt)

        vault = self._folder_settings.folder
        daily_dir = vault / folder_name
        daily_dir.mkdir(parents=True, exist_ok=True)
        file_path = daily_dir / f"{today_str}.md"

        if file_path.exists():
            idx = self._find_tab_for_file(file_path)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
                return
            tab = self._add_tab()
            tab.load_file(file_path)
            self._refresh_tab_title(tab)
            self._update_window_title()
            return

        # Create new daily note from template (if configured).
        tmpl_path = self._s.daily_notes_template()
        content = ""
        if tmpl_path:
            p = Path(tmpl_path)
            if not p.is_absolute():
                p = vault / p
            if p.is_file():
                content = TemplatePicker.resolve_content(p, title=today_str)

        file_path.write_text(content, encoding="utf-8")
        tab = self._add_tab()
        tab.load_file(file_path)
        self._refresh_tab_title(tab)
        self._update_window_title()

    def _on_save(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        if tab.file_path:
            if tab.save():
                self._refresh_tab_title(tab)
                if tab.file_path:
                    self._tree_panel.select_file(tab.file_path)
                    self._trigger_tags_scan()
                    self._save_history_snapshot(tab.file_path)
                self._update_metadata(tab)
                # Sync-on-save for manual saves
                if self._s.sync_on_save():
                    self._on_webdav_sync(auto_triggered=True)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        start_dir = str(self._folder_path) if self._folder_path else ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Markdown file"),
            start_dir,
            self.tr("Markdown files (*.md *.markdown);;All files (*)"),
        )
        if not path:
            return
        if tab.save_as(Path(path)):
            self._refresh_tab_title(tab)
            if tab.file_path:
                self._tree_panel.select_file(tab.file_path)
                self._trigger_tags_scan()

    # ------------------------------------------------------------------
    # Window title
    # ------------------------------------------------------------------
    def _update_window_title(self) -> None:
        tab = self._current_tab()
        if tab:
            display = tab.display_name()
        else:
            display = "CuteMD"
        self.setWindowTitle(self.tr("{} \u2013 CuteMD").format(display))

        # Status bar
        if self._folder_path:
            tab = self._current_tab()
            if tab and tab.file_path:
                try:
                    rel = tab.file_path.relative_to(self._folder_path)
                    self._status_file.setText(str(rel))
                except ValueError:
                    self._status_file.setText(str(tab.file_path))
            else:
                self._status_file.setText(str(self._folder_path.resolve()))
            self._status_file.setToolTip(str(self._folder_path.resolve()))
        else:
            self._status_file.setText(self.tr("Edit mode"))
            self._status_file.setToolTip("")

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def _retranslate_ui(self) -> None:
        """Refresh all user-visible strings after a language change."""
        # Actions
        self.act_open_folder.setText(self.tr("Open &Folder…"))
        self.act_close_folder.setText(self.tr("Close Folder"))
        self.act_new.setText(self.tr("&New File…"))
        self.act_save.setText(self.tr("&Save"))
        self.act_save_as.setText(self.tr("Save &As…"))
        self.act_close_tab.setText(self.tr("Close Tab"))
        self.act_exit.setText(self.tr("E&xit"))
        self.act_undo.setText(self.tr("&Undo"))
        self.act_redo.setText(self.tr("&Redo"))
        self.act_find.setText(self.tr("&Find…"))
        self.act_find_files.setText(self.tr("Find in &Files…"))
        self.act_replace_files.setText(self.tr("Replace in &Files…"))
        self.act_insert_table.setText(self.tr("Insert &Table…"))
        self.act_toggle_preview.setText(self.tr("Toggle &Preview"))
        self.act_toggle_split.setText(self.tr("Toggle Split &Orientation"))
        self.act_toggle_tree.setText(self.tr("Toggle &File Tree"))
        self.act_toggle_statusbar.setText(self.tr("Toggle Status &Bar"))
        self.act_settings.setText(self.tr("&Settings…"))
        self.act_shortcuts.setText(self.tr("&Keyboard Shortcuts…"))
        self.act_check_update.setText(self.tr("Check for &Updates…"))
        self.act_command_palette.setText(self.tr("&Command Palette…"))
        self.act_webdav_sync.setText(self.tr("&Sync Now"))
        self.act_export_html.setText(self.tr("Export as &HTML…"))
        self.act_export_pdf.setText(self.tr("Export as &PDF…"))
        self.act_export_odt.setText(self.tr("Export as &ODT…"))
        self.act_export_docx.setText(self.tr("Export as DOC&X…"))
        self.act_zoom_in.setText(self.tr("Zoom &In (Editor)"))
        self.act_zoom_out.setText(self.tr("Zoom &Out (Editor)"))
        self.act_zoom_reset.setText(self.tr("&Reset Zoom"))
        self.act_zoom_preview_in.setText(self.tr("Zoom Preview &In"))
        self.act_zoom_preview_out.setText(self.tr("Zoom Preview O&ut"))

        # Menu titles
        self._action_registry.menu("file").setTitle(self.tr("&File"))
        self._action_registry.menu("edit").setTitle(self.tr("&Edit"))
        self._action_registry.menu("view").setTitle(self.tr("&View"))
        self._action_registry.menu("settings").setTitle(self.tr("&Settings"))
        self._action_registry.menu("help").setTitle(self.tr("&Help"))
        if self._action_registry.menu("export"):
            self._action_registry.menu("export").setTitle(self.tr("E&xport as"))

        # Toolbar tooltips
        if hasattr(self, "_editor_toolbar"):
            self._editor_toolbar.retranslate()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._update_window_title()
            self._retranslate_ui()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        self._autosave_timer.stop()
        self._auto_sync_timer.stop()
        self._backlinks_timer.stop()
        self._tags_timer.stop()
        for i in range(self._tabs.count() - 1, -1, -1):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and not tab.maybe_save():
                event.ignore()
                return
        self._window_state.on_close(
            folder_path=self._folder_path,
            splitter_sizes=(
                self._splitter.sizes()[0] if len(self._splitter.sizes()) > 0 else 0,
                self._splitter.sizes()[1] if len(self._splitter.sizes()) > 1 else 0,
            ),
            left_splitter_sizes=self._left_splitter.sizes() if hasattr(self, "_left_splitter") else [],
            right_dock_sizes=self._right_splitter.sizes() if hasattr(self, "_right_splitter") else [],
            right_panel_width=self._splitter.sizes()[2] if len(self._splitter.sizes()) > 2 else 0,
            window_geometry=self.saveGeometry(),
        )
        event.accept()

    def sizeHint(self) -> QSize:
        return QSize(1200, 750)
