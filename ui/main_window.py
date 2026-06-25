"""Main window for the Markdown editor."""

import re
import sys
from pathlib import Path
from typing import Any

from core.logging import setup_logging

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
    QAction,
    QColor,
    QIcon,
    QKeySequence,
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
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import theme
from ui.animation_speed import animation_duration_ms
from ui.editor_context_menu import show_editor_context_menu
from ui.editor_tab import EditorTab
from ui.editor_toolbar import EditorToolbar
from ui.file_tree_panel import FileTreePanel
from ui.folder_settings import FolderSettings
from ui.search_panel import SearchPanel
from ui.settings_manager import AppSettings
from ui.shortcut_manager import ShortcutManager
from ui.theme_manager import ThemeManager
from ui.themes import get_theme, system_theme
from ui.toc_panel import TocPanel
from ui.webdav_sync import sync_folder

# ---------------------------------------------------------------------------
# Paths (supports PyInstaller one-file bundles)
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    _ROOT = Path(__file__).resolve().parent.parent
_CSS_PATH = _ROOT / "ui" / "preview_styles.css"
_ICONS_DIR = _ROOT / "ui" / "icons"

_LOG = setup_logging("cutemd.main_window")

# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, files_to_open: list[Path] | None = None) -> None:
        super().__init__()
        self._folder_path: Path | None = None
        self._folder_settings: FolderSettings | None = None
        self._files_to_open = files_to_open
        self._preview_visible = True

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
        _LOG.debug("__init__: editor_font=%s %d preview_font=%s %d", self._editor_font_family, self._editor_font_size, self._preview_font_family, self._preview_font_size)

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

        # Load custom CSS once
        self._preview_css = _CSS_PATH.read_text() if _CSS_PATH.exists() else ""

        # --- Markdown parser (shared across all tabs) ---
        from markdown_it import MarkdownIt
        from mdit_py_plugins.dollarmath import dollarmath_plugin

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
        )
        self._md.renderer.rules["math_inline"] = render_math_inline  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_inline_double"] = render_math_inline_double  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block"] = render_math_block  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block_label"] = render_math_block_label  # pyright: ignore[reportAttributeAccessIssue]
        _LOG.debug("__init__: markdown parser ready")

        # --- UI ---
        self.setWindowTitle("CuteMD - Markdown Editor")

        # Restore saved window geometry, or fall back to default size
        geometry = self._s.window_geometry()
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 750)

        self._setup_actions()
        self._setup_menubar()

        self._all_actions: dict[str, QAction] = {
            "act_open_folder": self.act_open_folder,
            "act_close_folder": self.act_close_folder,
            "act_new": self.act_new,
            "act_save": self.act_save,
            "act_save_as": self.act_save_as,
            "act_close_tab": self.act_close_tab,
            "act_exit": self.act_exit,
            "act_undo": self.act_undo,
            "act_redo": self.act_redo,
            "act_find": self.act_find,
            "act_find_files": self.act_find_files,
            "act_replace_files": self.act_replace_files,
            "act_toggle_preview": self.act_toggle_preview,
            "act_toggle_split": self.act_toggle_split,
            "act_toggle_tree": self.act_toggle_tree,
            "act_toggle_statusbar": self.act_toggle_statusbar,
            "act_settings": self.act_settings,
            "act_shortcuts": self.act_shortcuts,
            "act_webdav_sync": self.act_webdav_sync,
            "act_zoom_in": self.act_zoom_in,
            "act_zoom_out": self.act_zoom_out,
            "act_zoom_reset": self.act_zoom_reset,
            "act_zoom_preview_in": self.act_zoom_preview_in,
            "act_zoom_preview_out": self.act_zoom_preview_out,
        }
        self._shortcut_mgr = ShortcutManager(None)
        self._shortcut_mgr.apply(self._all_actions)

        self._setup_statusbar()
        self._setup_central()
        self._apply_theme()

        # Restore last folder (or prompt on first run)
        QTimer.singleShot(0, self._restore_last_folder)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_panel_restored", False):
            self._panel_restored = True
            self._reset_save_timer()

    def _reset_save_timer(self) -> None:
        """Ignore splitterMoved for 500ms after programmatic setSizes."""
        self._save_allowed = False
        if hasattr(self, "_save_timer"):
            self._save_timer.stop()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._allow_save)
        self._save_timer.start(500)

    def _allow_save(self) -> None:
        self._save_allowed = True

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        if not getattr(self, "_save_allowed", True):
            return
        left = self._splitter.sizes()[0]
        if left <= 0:
            return
        _LOG.debug("splitterMoved save: left=%d", left)
        self._s.set_left_panel_width(left)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _setup_actions(self) -> None:
        # File
        self.act_open_folder = QAction(self.tr("Open &Folder…"), self)
        self.act_open_folder.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open_folder.triggered.connect(self._on_open_folder)

        self.act_close_folder = QAction(self.tr("Close Folder"), self)
        self.act_close_folder.triggered.connect(self._on_close_folder)

        self.act_new = QAction(self.tr("&New File…"), self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self._on_new)

        self.act_save = QAction(self.tr("&Save"), self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._on_save)

        self.act_save_as = QAction(self.tr("Save &As…"), self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self._on_save_as)

        self.act_close_tab = QAction(self.tr("Close Tab"), self)
        self.act_close_tab.setShortcut(QKeySequence.StandardKey.Close)
        self.act_close_tab.triggered.connect(self._on_close_tab)

        self.act_exit = QAction(self.tr("E&xit"), self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_exit.triggered.connect(self.close)

        # Edit
        self.act_undo = QAction(self.tr("&Undo"), self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)

        self.act_redo = QAction(self.tr("&Redo"), self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)

        self.act_find = QAction(self.tr("&Find…"), self)
        self.act_find.setShortcut(QKeySequence.StandardKey.Find)
        self.act_find.triggered.connect(self._on_find)

        self.act_find_files = QAction(self.tr("Find in &Files…"), self)
        self.act_find_files.setShortcut(
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_F)
        )
        self.act_find_files.triggered.connect(self._on_find_in_files)

        self.act_replace_files = QAction(self.tr("Replace in &Files…"), self)
        self.act_replace_files.setShortcut(
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_H)
        )
        self.act_replace_files.triggered.connect(self._on_replace_in_files)

        # View
        self.act_toggle_preview = QAction(self.tr("Toggle &Preview"), self)
        self.act_toggle_preview.setCheckable(True)
        self.act_toggle_preview.setChecked(True)
        self.act_toggle_preview.toggled.connect(self._on_toggle_preview)

        self.act_toggle_split = QAction(self.tr("Toggle Split &Orientation"), self)
        self.act_toggle_split.triggered.connect(self._toggle_split)

        self.act_toggle_tree = QAction(self.tr("Toggle &File Tree"), self)
        self.act_toggle_tree.setCheckable(True)
        self.act_toggle_tree.setChecked(True)
        self.act_toggle_tree.setShortcut(QKeySequence("Ctrl+B"))
        self.act_toggle_tree.toggled.connect(self._on_toggle_tree)

        self.act_toggle_statusbar = QAction(self.tr("Toggle Status &Bar"), self)
        self.act_toggle_statusbar.setCheckable(True)
        self.act_toggle_statusbar.setChecked(True)
        self.act_toggle_statusbar.toggled.connect(self._on_toggle_statusbar)

        self.act_settings = QAction(self.tr("&Settings…"), self)
        self.act_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.act_settings.triggered.connect(self._on_settings)

        self.act_shortcuts = QAction(self.tr("&Keyboard Shortcuts…"), self)
        self.act_shortcuts.setShortcut(QKeySequence("Ctrl+/"))
        self.act_shortcuts.triggered.connect(self._on_show_shortcuts)

        self.act_webdav_sync = QAction(self.tr("&Sync Now"), self)
        self.act_webdav_sync.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_webdav_sync.triggered.connect(self._on_webdav_sync)

        # Zoom
        self.act_zoom_in = QAction(self.tr("Zoom &In (Editor)"), self)
        self.act_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        self.act_zoom_in.triggered.connect(lambda: self._zoom_editor(1))

        self.act_zoom_out = QAction(self.tr("Zoom &Out (Editor)"), self)
        self.act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.act_zoom_out.triggered.connect(lambda: self._zoom_editor(-1))

        self.act_zoom_reset = QAction(self.tr("&Reset Zoom"), self)
        self.act_zoom_reset.setShortcut(QKeySequence("Ctrl+0"))
        self.act_zoom_reset.triggered.connect(self._zoom_reset)

        self.act_zoom_preview_in = QAction(self.tr("Zoom Preview &In"), self)
        self.act_zoom_preview_in.setShortcut(QKeySequence("Ctrl+Shift+="))
        self.act_zoom_preview_in.triggered.connect(lambda: self._zoom_preview(1))

        self.act_zoom_preview_out = QAction(self.tr("Zoom Preview O&ut"), self)
        self.act_zoom_preview_out.setShortcut(QKeySequence("Ctrl+Shift+-"))
        self.act_zoom_preview_out.triggered.connect(lambda: self._zoom_preview(-1))

    # ------------------------------------------------------------------
    # Menubar
    # ------------------------------------------------------------------
    def _setup_menubar(self) -> None:
        mb = self.menuBar()

        self._file_menu = mb.addMenu(self.tr("&File"))
        self._file_menu.addAction(self.act_new)
        self._file_menu.addAction(self.act_save)
        self._file_menu.addAction(self.act_save_as)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.act_webdav_sync)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.act_close_tab)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.act_exit)

        self._edit_menu = mb.addMenu(self.tr("&Edit"))
        self._edit_menu.addAction(self.act_undo)
        self._edit_menu.addAction(self.act_redo)
        self._edit_menu.addSeparator()
        self._edit_menu.addAction(self.act_find)
        self._edit_menu.addAction(self.act_find_files)
        self._edit_menu.addAction(self.act_replace_files)

        self._view_menu = mb.addMenu(self.tr("&View"))
        self._view_menu.addAction(self.act_toggle_preview)
        self._view_menu.addAction(self.act_toggle_split)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self.act_toggle_tree)
        self._view_menu.addAction(self.act_toggle_statusbar)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self.act_zoom_in)
        self._view_menu.addAction(self.act_zoom_out)
        self._view_menu.addAction(self.act_zoom_reset)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self.act_zoom_preview_in)
        self._view_menu.addAction(self.act_zoom_preview_out)

        self._settings_menu = mb.addMenu(self.tr("&Settings"))
        self._settings_menu.addAction(self.act_settings)

        self._help_menu = mb.addMenu(self.tr("&Help"))
        self._help_menu.addAction(self.act_shortcuts)

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
            b.setIcon(self._make_colored_icon(name, icon_color))
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

        self._side_toc_btn = _side_btn(
            "toc", self.tr("Table of Contents"), slot=self._on_side_toc_toggled
        )
        lt_layout.addWidget(self._side_toc_btn)

        lt_layout.addStretch()

        self._side_folder_btn = QToolButton()
        self._side_folder_btn.setIcon(
            self._make_colored_icon("folder_switch", icon_color)
        )
        self._side_folder_btn.setToolTip(self.tr("Switch folder"))
        self._side_folder_btn.setAutoRaise(True)
        self._side_folder_btn.setIconSize(QSize(18, 18))
        self._side_folder_btn.setFixedSize(36, 30)
        self._side_folder_btn.clicked.connect(self._on_open_folder)
        self._sidebar_buttons.append((self._side_folder_btn, "folder_switch"))
        lt_layout.addWidget(self._side_folder_btn)

        # --- File tree panel ---
        self._tree_panel = FileTreePanel()
        self._tree_panel.file_activated.connect(self._on_tree_file_activated)
        self._tree_panel.file_double_activated.connect(self._on_tree_file_double_activated)
        self._tree_panel.file_open_new_tab.connect(self._on_tree_file_new_tab)
        self._tree_panel.file_renamed.connect(self._on_tree_file_renamed)
        self._tree_panel.file_deleted.connect(self._on_tree_file_deleted)
        self._tree_panel.set_show_hidden_files(self._show_hidden_files)

        # --- Search panel ---
        self._search_panel = SearchPanel()
        self._search_panel.file_activated.connect(
            lambda path, line: self._open_file_at_line((path, line))
        )

        # --- Left stack (tree / search / toc) ---
        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self._tree_panel)
        self._left_stack.addWidget(self._search_panel)

        self._toc_panel = TocPanel()
        self._toc_panel.heading_activated.connect(self._on_toc_heading_activated)
        self._left_stack.addWidget(self._toc_panel)

        # --- Tabs ---
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # --- Editor toolbar ---
        self._editor_toolbar = EditorToolbar(
            icon_color,
            lambda name, color, size=18: self._make_colored_icon(name, color, size),
        )
        self._editor_toolbar.format_requested.connect(self._insert_md)
        self._editor_toolbar.image_requested.connect(self._on_insert_image)
        editor_toolbar = self._editor_toolbar

        # --- Inline status bar ---
        self._status_file = QLabel("...")
        self._status_sync = QLabel("")
        self._status_encoding = QLabel("")
        self._status_cursor = QLabel("Ln 1, Col 1")
        self._status_words = QLabel("0 words")
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
        editor_layout.setSpacing(2)
        editor_layout.addWidget(editor_toolbar)
        editor_layout.addWidget(self._tabs)
        editor_layout.addWidget(status_widget)

        # Splitter: left_stack | editor_pane  (toolbar is outside, always visible)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._left_stack)
        self._splitter.addWidget(editor_pane)
        self._splitter.setSizes([220, 948])
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

        # Main layout: toolbar | splitter  (no splitter handle between them)
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._left_tb)
        outer_layout.addWidget(self._splitter)

        self.setCentralWidget(outer)

        # Hide QMainWindow status bar
        self.statusBar().hide()

        # Initial: tree visible, search hidden (block signals to skip layout while not yet shown)
        self._side_tree_btn.blockSignals(True)
        self._side_tree_btn.setChecked(True)
        self._side_tree_btn.blockSignals(False)
        self._left_stack.setCurrentIndex(0)

        self._preview_tab: EditorTab | None = None
        _LOG.debug("_setup_central: done")
        self._add_tab()

    # ------------------------------------------------------------------
    # Search panel (embedded find-in-files)
    # ------------------------------------------------------------------
    def _show_left_panel(self) -> None:
        _LOG.debug("_show_left_panel")
        self._left_stack.show()
        total = self._splitter.width()
        left = self._s.left_panel_width()
        _LOG.debug("_show_left_panel: total=%d saved_left=%d", total, left)
        if total > 0:
            self._animate_splitter_to(left)
        else:
            self._animate_splitter_to(220)

    def _hide_left_panel(self) -> None:
        _LOG.debug("_hide_left_panel")
        self._animate_splitter_to(0, on_finish=lambda: self._left_stack.hide())

    def _animate_splitter_to(self, left_width: int, on_finish=None) -> None:
        """Animate the main splitter's left panel width."""
        total = self._splitter.width()
        _LOG.debug("_animate_splitter_to: left=%d total=%d", left_width, total)
        if total <= 0:
            if on_finish:
                on_finish()
            return

        if hasattr(self, "_tree_anim"):
            self._tree_anim.stop()
        start = self._splitter.sizes()[0]

        self._splitter.setUpdatesEnabled(False)

        self._tree_anim = QVariantAnimation(self)
        self._tree_anim.setDuration(animation_duration_ms(150))
        self._tree_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._tree_anim.setStartValue(0.0)
        self._tree_anim.setEndValue(1.0)

        def _step(progress: float) -> None:
            cur = int(start + (left_width - start) * progress)
            self._splitter.setSizes([max(cur, 0), max(total - cur, 0)])

        self._tree_anim.valueChanged.connect(_step)

        def _done() -> None:
            self._splitter.setUpdatesEnabled(True)
            self._reset_save_timer()
            if on_finish:
                on_finish()

        self._tree_anim.finished.connect(_done)
        self._tree_anim.start()

    def _restore_panel_width(self) -> None:
        left = self._s.left_panel_width()
        total = self._splitter.width()
        _LOG.debug("_restore_panel_width: left=%d total=%d", left, total)
        if total > 0 and left >= 0:
            left = max(0, min(left, total))
            self._splitter.setSizes([left, total - left])
        self._reset_save_timer()

    def _on_side_tree_toggled(self, checked: bool) -> None:
        if checked:
            self._side_search_btn.blockSignals(True)
            self._side_search_btn.setChecked(False)
            self._side_search_btn.blockSignals(False)
            self._side_toc_btn.blockSignals(True)
            self._side_toc_btn.setChecked(False)
            self._side_toc_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(0)
            self._show_left_panel()
        else:
            self._hide_left_panel()

    def _on_side_search_toggled(self, checked: bool) -> None:
        if checked:
            self._side_tree_btn.blockSignals(True)
            self._side_tree_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_toc_btn.blockSignals(True)
            self._side_toc_btn.setChecked(False)
            self._side_toc_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(1)
            self._show_left_panel()
        else:
            self._hide_left_panel()

    def _on_side_toc_toggled(self, checked: bool) -> None:
        if checked:
            self._side_tree_btn.blockSignals(True)
            self._side_tree_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_search_btn.blockSignals(True)
            self._side_search_btn.setChecked(False)
            self._side_search_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(2)
            self._show_left_panel()
            self._rebuild_toc()
        else:
            self._hide_left_panel()

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
    # Tab management
    # ------------------------------------------------------------------
    def _add_tab(self) -> EditorTab:
        tab = EditorTab(
            self._md,
            self._preview_css,
            "dark" if self._current_theme.is_dark else "light",
            editor_font_family=self._editor_font_family,
            editor_font_size=self._editor_font_size,
            preview_font_family=self._preview_font_family,
            preview_font_size=self._preview_font_size,
            smart_editing=self._smart_editing,
            cursor_width=getattr(self, "_cursor_width", 2),
        )
        tab.set_line_number_mode(self._line_number_mode)
        tab.modified_changed.connect(self._on_tab_modified)
        tab.status_changed.connect(self._on_tab_status)
        tab.title_changed.connect(lambda: self._refresh_tab_title(tab))
        tab.file_link_clicked.connect(
            lambda target, t=tab: self._on_file_link_clicked(t, target)
        )
        tab.encoding_changed.connect(self._on_tab_encoding_changed)

        # Right-click context menu on the editor
        tab.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab.editor.customContextMenuRequested.connect(self._on_editor_context_menu)

        # Live TOC update
        tab.editor.textChanged.connect(self._on_editor_text_changed)

        idx = self._tabs.addTab(tab, tab.display_name())
        self._tabs.setTabToolTip(idx, tab.tooltip())
        self._tabs.setCurrentIndex(idx)
        self._connect_edit_actions(tab)

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

    def _on_tab_changed(self, index: int) -> None:
        _LOG.debug("_on_tab_changed: index=%d", index)
        tab = self._current_tab()
        if tab:
            self._connect_edit_actions(tab)
            tab._emit_status()
            self._update_window_title()
            # Rebuild TOC if the panel is visible
            if self._side_toc_btn.isChecked():
                self._rebuild_toc()

    def _on_editor_text_changed(self) -> None:
        """Rebuild TOC when editor content changes (only if TOC is open)."""
        if self._side_toc_btn.isChecked():
            self._rebuild_toc()

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
        if isinstance(tab, EditorTab) and not tab.maybe_save():
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
    def _make_colored_icon(self, name: str, color: QColor, size: int = 18) -> QIcon:
        """Render an SVG icon tinted with *color*."""
        from PySide6.QtSvg import QSvgRenderer

        path = str(_ICONS_DIR / f"{name}.svg")
        renderer = QSvgRenderer(path)

        svg = QPixmap(size, size)
        svg.fill(Qt.GlobalColor.transparent)
        painter = QPainter(svg)
        renderer.render(painter)
        painter.end()

        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.drawPixmap(0, 0, svg)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(result.rect(), color)
        painter.end()

        return QIcon(result)

    def _recolor_toolbar_icons(self) -> None:
        icon_color = self._current_theme.icon_color
        for button, name in getattr(self, "_sidebar_buttons", []):
            button.setIcon(self._make_colored_icon(name, icon_color))
        if hasattr(self, "_editor_toolbar"):
            self._editor_toolbar.recolor(icon_color)

    def _on_find(self) -> None:
        tab = self._current_tab()
        if isinstance(tab, EditorTab):
            tab.open_find()

    def _on_find_in_files(self) -> None:
        _LOG.debug("_on_find_in_files")
        if self._folder_path is None:
            return
        if self._left_stack.currentIndex() == 1 and not self._left_stack.isHidden():
            self._side_search_btn.blockSignals(True)
            self._side_search_btn.setChecked(False)
            self._side_search_btn.blockSignals(False)
            self._hide_left_panel()
        else:
            self._side_search_btn.blockSignals(True)
            self._side_tree_btn.blockSignals(True)
            self._side_toc_btn.blockSignals(True)
            self._side_search_btn.setChecked(True)
            self._side_tree_btn.setChecked(False)
            self._side_toc_btn.setChecked(False)
            self._side_search_btn.blockSignals(False)
            self._side_tree_btn.blockSignals(False)
            self._side_toc_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(1)
            self._show_left_panel()
            self._search_panel._search_input.setFocus()
            self._search_panel._search_input.selectAll()

    def _on_replace_in_files(self) -> None:  # Apre/chiude replacement
        _LOG.debug("_on_replace_in_files")
        if self._folder_path is None:
            return
        if self._left_stack.currentIndex() == 1 and not self._left_stack.isHidden():
            self._search_panel._replace_input.setFocus()
            self._search_panel._replace_input.selectAll()
        else:
            self._side_search_btn.blockSignals(True)
            self._side_tree_btn.blockSignals(True)
            self._side_toc_btn.blockSignals(True)
            self._side_search_btn.setChecked(True)
            self._side_tree_btn.setChecked(False)
            self._side_toc_btn.setChecked(False)
            self._side_search_btn.blockSignals(False)
            self._side_tree_btn.blockSignals(False)
            self._side_toc_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(1)
            self._show_left_panel()
            self._search_panel._replace_input.setFocus()
            self._search_panel._replace_input.selectAll()

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
        show_editor_context_menu(
            self,
            point,
            self._current_theme.icon_color,
            lambda name, color, size=18: self._make_colored_icon(name, color, size),
            self._insert_md,
            self._on_insert_image,
        )

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
        _LOG.debug("_apply_theme: %s", self._theme_id)
        from markdown.tools import set_pygments_style

        set_pygments_style(self._current_theme.pygments_style)

        pal = self._current_theme.build_palette()
        app = QApplication.instance()
        if app is not None:
            app.setPalette(pal)
            app.setStyleSheet(theme.load_qss(pal))

        self._recolor_toolbar_icons()
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab.set_theme(
                    "dark" if self._current_theme.is_dark else "light",
                    self._current_theme.pygments_style,
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

        if self._folder_settings is not None:
            cfg = self._folder_settings.load_webdav_config()
            if cfg:
                webdav_url = cfg.get("url", "")
                webdav_user = cfg.get("username", "")
                webdav_pass = cfg.get("password", "")

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
            self._folder_settings,
            self,
            current_webdav_url=webdav_url,
            current_webdav_user=webdav_user,
            current_webdav_pass=webdav_pass,
            current_autosave_interval=self._s.autosave_interval(),
            current_auto_sync_enabled=self._s.auto_sync_enabled(),
            current_auto_sync_interval=self._s.auto_sync_interval(),
            current_sync_on_save=self._s.sync_on_save(),
            current_session_restore_enabled=self._s.session_restore_enabled(),
            current_show_hidden_files=self._show_hidden_files,
        )
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return

        _LOG.debug("_on_settings: applying changes")

        # --- Theme ---
        new_theme_id = dlg.selected_theme_id()
        if new_theme_id != self._theme_id:
            self._theme_id = new_theme_id
            self._current_theme = (
                system_theme() if new_theme_id == "system" else get_theme(new_theme_id)
            )
            self._apply_theme()

        # --- Language ---
        new_lang = dlg.selected_language()
        if new_lang != self._language:
            self._language = new_lang
            self._s.set_language(new_lang)
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
        if new_ef != self._editor_font_family or new_efs != self._editor_font_size:
            self._editor_font_family = new_ef
            self._editor_font_size = new_efs
            changed = True

        if new_pf != self._preview_font_family or new_pfs != self._preview_font_size:
            self._preview_font_family = new_pf
            self._preview_font_size = new_pfs
            changed = True

        if changed:
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_editor_font(
                        self._editor_font_family, self._editor_font_size
                    )
                    tab.set_preview_font(
                        self._preview_font_family, self._preview_font_size
                    )

        # --- Line numbers ---
        new_ln = dlg.selected_line_number_mode()
        if new_ln != self._line_number_mode:
            self._line_number_mode = new_ln
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_line_number_mode(new_ln)

        # --- Cursor width ---
        new_cw = dlg.selected_cursor_width()
        if new_cw != self._cursor_width:
            self._cursor_width = new_cw
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_cursor_width(new_cw)

        # --- Smart editing ---
        new_se = dlg.selected_smart_editing()
        new_ls = dlg.selected_link_style()
        new_se["link_style"] = new_ls
        if new_se != self._smart_editing:
            self._smart_editing = new_se
            for key, val in new_se.items():
                self._s.set_raw_value(f"smart_editing/{key}", val)
            self._s.set_raw_value("link_style", new_ls)
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_smart_editing(new_se)

        # --- Autosave interval ---
        new_asi = dlg.selected_autosave_interval()
        if new_asi != self._s.autosave_interval():
            self._s.set_autosave_interval(new_asi)
            self._autosave_interval = max(1, new_asi) * 1000
            self._autosave_timer.setInterval(self._autosave_interval)

        # --- Per-folder settings (shortcuts, images, WebDAV, appearance) ---
        if self._folder_settings is not None:
            new_sc = dlg.selected_shortcuts()
            self._folder_settings.save_shortcuts(new_sc)

            cfg = self._folder_settings.load()
            new_id = dlg.selected_attachments_dir()
            if new_id is not None:
                cfg["attachments_dir"] = new_id

            cfg["theme"] = self._theme_id
            cfg["editor_font_family"] = self._editor_font_family
            cfg["editor_font_size"] = self._editor_font_size
            cfg["preview_font_family"] = self._preview_font_family
            cfg["preview_font_size"] = self._preview_font_size
            cfg["line_number_mode"] = self._line_number_mode
            cfg["cursor_width"] = self._cursor_width
            self._folder_settings.save(cfg)

            self._shortcut_mgr = ShortcutManager(self._folder_settings)
            self._shortcut_mgr.apply(self._all_actions)

            # Propagate updated attachments_dir to all open tabs
            attachments_dir = self._folder_settings.attachments_dir()
            for i in range(self._tabs.count()):
                w = self._tabs.widget(i)
                if isinstance(w, EditorTab):
                    w.set_attachments_dir(attachments_dir)

            # --- WebDAV config ---
            new_url = dlg.selected_webdav_url()
            new_user = dlg.selected_webdav_username()
            new_pass = dlg.selected_webdav_password()

            if new_url or new_user or new_pass:
                self._folder_settings.save_webdav_config(
                    {
                        "url": new_url,
                        "username": new_user,
                        "password": new_pass,
                    }
                )
            else:
                self._folder_settings.clear_webdav_config()

            # --- Auto-sync settings ---
            self._s.set_auto_sync_enabled(dlg.selected_auto_sync_enabled())
            self._s.set_auto_sync_interval(dlg.selected_auto_sync_interval())
            self._s.set_sync_on_save(dlg.selected_sync_on_save())

            # --- Session restore ---
            self._s.set_session_restore_enabled(dlg.selected_session_restore_enabled())

            self._update_auto_sync_timer()

            self._update_menu_state()
        else:
            # No folder open — persist to global QSettings
            self._s.set_theme(self._theme_id)
            self._s.set_editor_font_family(self._editor_font_family)
            self._s.set_editor_font_size(self._editor_font_size)
            self._s.set_preview_font_family(self._preview_font_family)
            self._s.set_preview_font_size(self._preview_font_size)
            self._s.set_line_number_mode(self._line_number_mode)
            self._s.set_cursor_width(self._cursor_width)

        # --- Show hidden files (global) ---
        new_shf = dlg.selected_show_hidden_files()
        if new_shf != self._show_hidden_files:
            self._show_hidden_files = new_shf
            self._s.set_show_hidden_files(new_shf)
            self._tree_panel.set_show_hidden_files(new_shf)

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

        from ui.webdav_sync import SyncResult, SyncThread

        if not webdav_url:
            if not auto_triggered:
                QMessageBox.warning(
                    self, self.tr("Sync"), self.tr("WebDAV URL is not configured.")
                )
            return

        self._sync_busy = True
        self._status_sync.setText(self.tr("Syncing..."))
        self._sync_thread = SyncThread(self._folder_path, webdav_url, user, pwd)

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
                parts.append(self.tr("{} conflicts skipped").format(len(r.conflicts_skipped)))
            status = ", ".join(parts) if parts else self.tr("Sync completed")
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

        actions = {
            "act_open_folder": self.act_open_folder,
            "act_close_folder": self.act_close_folder,
            "act_new": self.act_new,
            "act_save": self.act_save,
            "act_save_as": self.act_save_as,
            "act_close_tab": self.act_close_tab,
            "act_exit": self.act_exit,
            "act_undo": self.act_undo,
            "act_redo": self.act_redo,
            "act_find": self.act_find,
            "act_find_files": self.act_find_files,
            "act_replace_files": self.act_replace_files,
            "act_toggle_preview": self.act_toggle_preview,
            "act_toggle_split": self.act_toggle_split,
            "act_toggle_tree": self.act_toggle_tree,
            "act_toggle_statusbar": self.act_toggle_statusbar,
            "act_zoom_in": self.act_zoom_in,
            "act_zoom_out": self.act_zoom_out,
            "act_zoom_reset": self.act_zoom_reset,
            "act_zoom_preview_in": self.act_zoom_preview_in,
            "act_zoom_preview_out": self.act_zoom_preview_out,
            "act_webdav_sync": self.act_webdav_sync,
            "act_settings": self.act_settings,
            "act_shortcuts": self.act_shortcuts,
        }
        dlg = ShortcutsDialog(actions, self)
        dlg.exec()

    def _on_toggle_tree(self, visible: bool) -> None:
        if visible:
            self._side_tree_btn.blockSignals(True)
            self._side_search_btn.blockSignals(True)
            self._side_toc_btn.blockSignals(True)
            self._side_tree_btn.setChecked(True)
            self._side_search_btn.setChecked(False)
            self._side_toc_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_search_btn.blockSignals(False)
            self._side_toc_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(0)
            self._show_left_panel()
        else:
            self._side_tree_btn.setChecked(False)
            self._side_search_btn.setChecked(False)
            self._side_toc_btn.setChecked(False)
            self._hide_left_panel()

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
            global_cfg = {
                "theme": self._s.theme(),
                "editor_font_family": self._editor_font_family,
                "editor_font_size": self._editor_font_size,
                "preview_font_family": self._preview_font_family,
                "preview_font_size": self._preview_font_size,
                "attachments_dir": "images",
            }
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

        self._shortcut_mgr = ShortcutManager(self._folder_settings)
        self._shortcut_mgr.apply(self._all_actions)
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._tree_panel.set_root_path(path)
        self._search_panel.set_folder(path)
        self._add_recent_folder(path)
        self._s.set_last_folder(path)
        self._update_auto_sync_timer()
        self._update_menu_state()

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
                if tab is not None and not tab.is_modified:
                    tab.load_file(fp)
                    self._refresh_tab_title(tab)
                else:
                    tab = self._add_tab()
                    tab.load_file(fp)
            self._update_menu_state()
            return

        # Try session restore first (if enabled and no CLI files)
        if self._restore_session():
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
        if not folder_mode:
            self._side_tree_btn.blockSignals(True)
            self._side_search_btn.blockSignals(True)
            self._side_toc_btn.blockSignals(True)
            self._side_tree_btn.setChecked(False)
            self._side_search_btn.setChecked(False)
            self._side_toc_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_search_btn.blockSignals(False)
            self._side_toc_btn.blockSignals(False)
            self._left_stack.hide()
            self._left_tb.hide()
            self.act_toggle_tree.setChecked(False)
            self._side_folder_btn.setText("...")
        else:
            self._side_tree_btn.blockSignals(True)
            self._side_search_btn.blockSignals(True)
            self._side_tree_btn.setChecked(True)
            self._side_search_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_search_btn.blockSignals(False)
            self._left_tb.show()
            self._left_stack.setCurrentIndex(0)
            self._left_stack.show()
            self.act_toggle_tree.setChecked(True)
            QTimer.singleShot(0, self._restore_panel_width)
            self._side_folder_btn.setText(self._folder_path.name)
        self._update_window_title()

    def _add_recent_folder(self, path: Path) -> None:
        recent = self._s.recent_folders()
        sp = str(path.resolve())
        recent = [p for p in recent if p != sp]
        recent.insert(0, sp)
        self._s.set_recent_folders(recent[:10])

    def _save_session(self) -> None:
        """Save the list of open tab file paths and current folder to settings."""
        tabs: list[str] = []
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and tab.file_path:
                tabs.append(str(tab.file_path))
        self._s.set_session_restore_tabs(tabs)
        if self._folder_path:
            self._s.set_raw_value("session_restore_folder", str(self._folder_path))
        else:
            self._s.set_raw_value("session_restore_folder", "")

    def _restore_session(self) -> bool:
        """Restore folder and open tabs from the last session. Returns True if any tabs restored."""
        _LOG.debug("_restore_session: enabled=%s", self._s.session_restore_enabled())
        if not self._s.session_restore_enabled():
            return False
        # Restore folder first if one was open
        folder_str = self._s.raw_value("session_restore_folder", "")
        if folder_str:
            folder = Path(folder_str)
            if folder.is_dir():
                self._set_folder(folder)
        saved_tabs = self._s.session_restore_tabs()
        _LOG.debug("_restore_session: folder=%s tabs=%d", folder_str, len(saved_tabs))
        if not saved_tabs:
            return False
        restored = 0
        for path_str in saved_tabs:
            p = Path(path_str)
            if p.is_file():
                tab = self._add_tab()
                tab.load_file(p)
                restored += 1
        if restored > 0:
            # Remove the untitled tab left by _set_folder / the initial one
            untitled = self._tabs.widget(0)
            if isinstance(untitled, EditorTab) and untitled.file_path is None:
                self._tabs.removeTab(0)
        return restored > 0

    def _on_close_folder(self) -> None:
        tab = self._current_tab()
        if tab and not tab.maybe_save():
            return
        self._folder_path = None
        self._folder_settings = None
        self._shortcut_mgr = ShortcutManager(None)
        self._shortcut_mgr.apply(self._all_actions)
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._tree_panel.set_root_path("")
        self._search_panel.set_folder(None)
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

    def _on_file_link_clicked(self, source_tab: EditorTab, target: str) -> None:
        """Click on a link/wikilink — open URL in browser or file in a tab."""
        # URLs → open in browser
        if target.startswith(("http://", "https://", "www.")):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            url = target if "://" in target else "https://" + target
            QDesktopServices.openUrl(QUrl(url))
            return

        path = self._resolve_link_target(target, source_tab.file_path)
        if path is None and self._folder_path is not None:
            # Try the configured attachments_dir first (fast).
            if self._folder_settings is not None:
                candidate = self._folder_settings.attachments_dir() / Path(target).name
                if candidate.is_file():
                    path = candidate.resolve()
            # Fall back to rglob in the folder.
            if path is None:
                from markdown.image_utils import _IMG_EXTS_RE

                stem = Path(target).stem.lower()
                is_img = bool(_IMG_EXTS_RE.search(target))
                for p in self._folder_path.rglob("*"):
                    if p.is_file() and p.stem.lower() == stem:
                        if is_img and _IMG_EXTS_RE.search(p.name):
                            path = p.resolve()
                            break
                        if not is_img and p.suffix.lower() in (".md", ".markdown"):
                            path = p.resolve()
                            break
        if path is None:
            return

        idx = self._find_tab_for_file(path)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
            return

        tab = self._add_tab()
        tab.load_file(path)
        self._refresh_tab_title(tab)
        self._update_window_title()

    @staticmethod
    def _resolve_link_target(target: str, source: Path | None) -> Path | None:
        """Resolve a link/wikilink target to an absolute ``Path``, or ``None``."""
        target_path = Path(target)
        if target_path.is_absolute():
            return target_path if target_path.exists() else None

        # Resolve relative to the source file's directory, if known
        if source is not None:
            base = source.parent
        else:
            base = Path.cwd()

        candidates = [base / target_path]
        if target_path.suffix.lower() not in (".md", ".markdown"):
            candidates.append(base / (target + ".md"))
            candidates.append(base / (target + ".markdown"))

        for p in candidates:
            if p.is_file():
                return p.resolve()

        return None

    def _on_autosave(self) -> None:
        """Autosave: silently save all modified tabs with a file path."""
        _LOG.debug("_on_autosave: triggering")
        saved_any = False
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                if tab.auto_save() is not False:
                    saved_any = True
        # Sync-on-save: trigger sync if enabled and something was saved
        if saved_any and self._s.sync_on_save():
            self._on_webdav_sync(auto_triggered=True)

    def _on_new(self) -> None:
        self._add_tab()
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
            "Save Markdown file",
            start_dir,
            "Markdown files (*.md *.markdown);;All files (*)",
        )
        if not path:
            return
        if tab.save_as(Path(path)):
            self._refresh_tab_title(tab)
            if tab.file_path:
                self._tree_panel.select_file(tab.file_path)

    # ------------------------------------------------------------------
    # Window title
    # ------------------------------------------------------------------
    def _update_window_title(self) -> None:
        tab = self._current_tab()
        if tab:
            display = tab.display_name()
        else:
            display = "CuteMD"
        self.setWindowTitle(f"{display} \u2013 CuteMD")

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
        self.act_toggle_preview.setText(self.tr("Toggle &Preview"))
        self.act_toggle_split.setText(self.tr("Toggle Split &Orientation"))
        self.act_toggle_tree.setText(self.tr("Toggle &File Tree"))
        self.act_toggle_statusbar.setText(self.tr("Toggle Status &Bar"))
        self.act_settings.setText(self.tr("&Settings…"))
        self.act_shortcuts.setText(self.tr("&Keyboard Shortcuts…"))
        self.act_webdav_sync.setText(self.tr("&Sync Now"))
        self.act_zoom_in.setText(self.tr("Zoom &In (Editor)"))
        self.act_zoom_out.setText(self.tr("Zoom &Out (Editor)"))
        self.act_zoom_reset.setText(self.tr("&Reset Zoom"))
        self.act_zoom_preview_in.setText(self.tr("Zoom Preview &In"))
        self.act_zoom_preview_out.setText(self.tr("Zoom Preview O&ut"))

        # Menu titles
        self._file_menu.setTitle(self.tr("&File"))
        self._edit_menu.setTitle(self.tr("&Edit"))
        self._view_menu.setTitle(self.tr("&View"))
        self._settings_menu.setTitle(self.tr("&Settings"))
        self._help_menu.setTitle(self.tr("&Help"))

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
        for i in range(self._tabs.count() - 1, -1, -1):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and not tab.maybe_save():
                event.ignore()
                return
        # Save session if enabled
        if self._s.session_restore_enabled():
            self._save_session()
        self._s.set_window_geometry(self.saveGeometry())
        left = self._splitter.sizes()[0]
        _LOG.debug("closeEvent: splitter sizes=%s saving left=%d", self._splitter.sizes(), left)
        if left > 0:
            self._s.set_left_panel_width(left)
            self._s._s.sync()
        else:
            _LOG.debug("closeEvent: left=%d, NOT saving (panel hidden?)", left)
        event.accept()

    def sizeHint(self) -> QSize:
        return QSize(1200, 750)
