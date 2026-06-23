"""Main window for the Markdown editor."""

import sys
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QSettings, QSize, Qt, QTimer
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
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import theme
from ui.editor_tab import EditorTab
from ui.file_tree_panel import FileTreePanel
from ui.folder_settings import FolderSettings
from ui.themes import get_theme, system_theme

# ---------------------------------------------------------------------------
# Paths (supports PyInstaller one-file bundles)
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    _ROOT = Path(__file__).resolve().parent.parent
_CSS_PATH = _ROOT / "ui" / "preview_styles.css"
_ICONS_DIR = _ROOT / "ui" / "icons"


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

        # Restore saved settings
        settings = QSettings("cutemd", "cutemd")
        self._theme_id = str(settings.value("theme", "system"))
        self._current_theme = (
            system_theme() if self._theme_id == "system" else get_theme(self._theme_id)
        )
        self._editor_font_family = str(settings.value("editor_font_family", "System"))
        # Backward compat: old settings used "Sistema"
        if self._editor_font_family == "Sistema":
            self._editor_font_family = "System"
        _raw = settings.value("editor_font_size", 11)
        self._editor_font_size = _raw if isinstance(_raw, int) else 11
        self._preview_font_family = str(settings.value("preview_font_family", "System"))
        if self._preview_font_family == "Sistema":
            self._preview_font_family = "System"
        _raw = settings.value("preview_font_size", 16)
        self._preview_font_size = _raw if isinstance(_raw, int) else 16
        self._language = str(settings.value("language", ""))
        _raw = settings.value("line_number_mode", 1)
        self._line_number_mode = _raw if isinstance(_raw, int) else 1

        self._smart_editing: dict[str, Any] = {
            "enabled": bool(settings.value("smart_editing/enabled", True)),
            "auto_pair": bool(settings.value("smart_editing/auto_pair", True)),
            "auto_pair_brackets": bool(settings.value("smart_editing/auto_pair_brackets", True)),
            "continue_lists": bool(settings.value("smart_editing/continue_lists", True)),
            "backspace_pairs": bool(settings.value("smart_editing/backspace_pairs", True)),
            "link_style": str(settings.value("link_style", "md")),
        }

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

        # --- UI ---
        self.setWindowTitle("CuteMD - Markdown Editor")

        # Restore saved window geometry, or fall back to default size
        geometry = settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 750)

        self._setup_actions()
        self._setup_menubar()
        self._setup_statusbar()
        self._setup_central()
        self._apply_theme()

        # Restore last folder (or prompt on first run)
        QTimer.singleShot(0, self._restore_last_folder)

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
        self._file_menu.addAction(self.act_close_tab)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.act_exit)

        self._edit_menu = mb.addMenu(self.tr("&Edit"))
        self._edit_menu.addAction(self.act_undo)
        self._edit_menu.addAction(self.act_redo)
        self._edit_menu.addSeparator()
        self._edit_menu.addAction(self.act_find)
        self._edit_menu.addAction(self.act_find_files)

        self._view_menu = mb.addMenu(self.tr("&View"))
        self._view_menu.addAction(self.act_toggle_preview)
        self._view_menu.addAction(self.act_toggle_split)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self.act_toggle_tree)
        self._view_menu.addAction(self.act_toggle_statusbar)

        self._settings_menu = mb.addMenu(self.tr("&Settings"))
        self._settings_menu.addAction(self.act_settings)

        self._help_menu = mb.addMenu(self.tr("&Help"))

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------
    def _setup_central(self) -> None:
        icon_color = self._current_theme.icon_color
        self._toolbar_buttons: list[tuple[QToolButton, str]] = []
        self._toolbar_tooltips: list[str] = []

        # --- Left vertical toolbar (ALWAYS visible, separate child in splitter) ---
        left_tb = QWidget()
        left_tb.setObjectName("leftToolbar")
        left_tb.setFixedWidth(32)
        left_tb.setMinimumWidth(32)
        lt_layout = QVBoxLayout(left_tb)
        lt_layout.setContentsMargins(0, 4, 0, 4)
        lt_layout.setSpacing(2)

        def _side_btn(name: str, tip: str, checkable: bool = True, slot=None) -> QToolButton:
            b = QToolButton()
            b.setIcon(self._make_colored_icon(name, icon_color))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            b.setFixedSize(28, 26)
            b.setCheckable(checkable)
            if slot:
                b.toggled.connect(slot)
            self._toolbar_buttons.append((b, name))
            return b

        self._side_tree_btn = _side_btn(
            "folder", self.tr("Toggle file tree"), slot=self._on_side_tree_toggled
        )
        lt_layout.addWidget(self._side_tree_btn)

        self._side_search_btn = _side_btn(
            "search", self.tr("Find in files"), slot=self._on_side_search_toggled
        )
        lt_layout.addWidget(self._side_search_btn)

        lt_layout.addStretch()

        self._side_folder_btn = QToolButton()
        self._side_folder_btn.setText("...")
        self._side_folder_btn.setToolTip(self.tr("Switch folder"))
        self._side_folder_btn.setAutoRaise(True)
        self._side_folder_btn.setFixedSize(28, 26)
        self._side_folder_btn.clicked.connect(self._on_open_folder)
        lt_layout.addWidget(self._side_folder_btn)

        # --- File tree panel ---
        self._tree_panel = FileTreePanel()
        self._tree_panel.file_activated.connect(self._on_tree_file_activated)
        self._tree_panel.file_open_new_tab.connect(self._on_tree_file_new_tab)

        # --- Search panel ---
        self._search_panel = self._make_search_panel()

        # --- Left stack (tree / search) ---
        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self._tree_panel)
        self._left_stack.addWidget(self._search_panel)

        # --- Tabs ---
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # --- Editor toolbar ---
        editor_toolbar = self._make_editor_toolbar()

        # --- Inline status bar ---
        self._status_file = QLabel("...")
        self._status_cursor = QLabel("Ln 1, Col 1")
        self._status_words = QLabel("0 words")
        status_widget = QWidget()
        status_widget.setObjectName("inlineStatusBar")
        sl = QHBoxLayout(status_widget)
        sl.setContentsMargins(8, 1, 8, 1)
        sl.addWidget(self._status_file, 1)
        sl.addWidget(self._status_cursor)
        sl.addWidget(self._status_words)

        # --- Editor pane ---
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(editor_toolbar)
        editor_layout.addWidget(self._tabs)
        editor_layout.addWidget(status_widget)

        # Splitter: left_stack | editor_pane  (toolbar is outside, always visible)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._left_stack)
        self._splitter.addWidget(editor_pane)
        self._splitter.setSizes([220, 948])

        # Main layout: toolbar | splitter  (no splitter handle between them)
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(left_tb)
        outer_layout.addWidget(self._splitter)

        self.setCentralWidget(outer)

        # Hide QMainWindow status bar
        self.statusBar().hide()

        # Initial: tree visible, search hidden (block signals to skip layout while not yet shown)
        self._side_tree_btn.blockSignals(True)
        self._side_tree_btn.setChecked(True)
        self._side_tree_btn.blockSignals(False)
        self._left_stack.setCurrentIndex(0)

        self._add_tab()

    # ------------------------------------------------------------------
    # Search panel (embedded find-in-files)
    # ------------------------------------------------------------------
    def _make_search_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(self.tr("Search files\u2026"))
        self._search_input.textChanged.connect(self._on_search_text_changed)

        case_row = QHBoxLayout()
        self._search_case_cb = QCheckBox(self.tr("Match case"))
        self._search_case_cb.toggled.connect(lambda: self._on_search_text_changed(self._search_input.text()))
        case_row.addWidget(self._search_case_cb)
        case_row.addStretch()

        self._search_results = QListWidget()
        self._search_results.itemDoubleClicked.connect(self._on_search_result_clicked)

        layout.addWidget(self._search_input)
        layout.addLayout(case_row)
        layout.addWidget(self._search_results)
        return panel

    def _on_search_text_changed(self, text: str) -> None:
        self._search_results.clear()
        if not text or self._folder_path is None:
            return
        flags = re.IGNORECASE if not self._search_case_cb.isChecked() else 0
        for md_path in self._folder_path.rglob("*.md"):
            try:
                content = md_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                if re.search(re.escape(text), line, flags):
                    rel = md_path.relative_to(self._folder_path)
                    item_text = f"{rel}:{line_num}: {line.strip()[:120]}"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, (md_path, line_num))
                    self._search_results.addItem(item)

    def _on_search_result_clicked(self, item: QListWidgetItem) -> None:
        location = item.data(Qt.ItemDataRole.UserRole)
        if location:
            self._open_file_at_line(location)

    def _show_left_panel(self) -> None:
        self._left_stack.show()
        self._splitter.setSizes([220, max(self._splitter.width() - 220, 200)])

    def _hide_left_panel(self) -> None:
        self._left_stack.hide()
        self._splitter.setSizes([0, max(self._splitter.width(), 200)])

    def _on_side_tree_toggled(self, checked: bool) -> None:
        if checked:
            self._side_search_btn.blockSignals(True)
            self._side_search_btn.setChecked(False)
            self._side_search_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(0)
            self._show_left_panel()
        else:
            self._hide_left_panel()

    def _on_side_search_toggled(self, checked: bool) -> None:
        if checked:
            self._side_tree_btn.blockSignals(True)
            self._side_tree_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(1)
            self._show_left_panel()
        else:
            self._hide_left_panel()

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
        )
        tab.set_line_number_mode(self._line_number_mode)
        tab.modified_changed.connect(self._on_tab_modified)
        tab.status_changed.connect(self._on_tab_status)
        tab.title_changed.connect(lambda: self._refresh_tab_title(tab))
        tab.file_link_clicked.connect(lambda target, t=tab: self._on_file_link_clicked(t, target))

        # Right-click context menu on the editor
        tab.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab.editor.customContextMenuRequested.connect(self._on_editor_context_menu)

        idx = self._tabs.addTab(tab, tab.display_name())
        self._tabs.setTabToolTip(idx, tab.tooltip())
        self._tabs.setCurrentIndex(idx)
        self._connect_edit_actions(tab)
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
                self._tabs.setTabText(i, tab.display_name())
                self._tabs.setTabToolTip(i, tab.tooltip())
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
        tab = self._current_tab()
        if tab:
            self._connect_edit_actions(tab)
            tab._emit_status()
            self._update_window_title()

    def _on_tab_modified(self, _modified: bool) -> None:
        self._update_window_title()

    def _on_tab_status(self, cursor: str, words: str) -> None:
        self._status_cursor.setText(cursor)
        self._status_words.setText(words)

    def _on_tab_close_requested(self, index: int) -> None:
        tab = self._tabs.widget(index)
        if isinstance(tab, EditorTab) and not tab.maybe_save():
            return
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

    def _make_editor_toolbar(self) -> QWidget:
        icon_color = self._current_theme.icon_color

        tb = QWidget()
        tb.setObjectName("editorToolbar")
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(1)

        def _sep() -> None:
            s = QWidget()
            s.setObjectName("toolbarSep")
            s.setFixedWidth(1)
            layout.addWidget(s)

        def _btn(icon_name: str, syntax: str, tip: str) -> None:
            b = QToolButton()
            b.setIcon(self._make_colored_icon(icon_name, icon_color))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            b.setFixedSize(28, 26)
            b.clicked.connect(lambda checked=False, s=syntax: self._insert_md(s))
            layout.addWidget(b)
            self._toolbar_buttons.append((b, icon_name))
            self._toolbar_tooltips.append(tip)

        # --- Heading button ---
        self._heading_btn = QToolButton()
        self._heading_btn.setIcon(self._make_colored_icon("heading", icon_color))
        self._heading_btn.setToolTip(self.tr("Heading level"))
        self._heading_btn.setAutoRaise(True)
        self._heading_btn.setIconSize(QSize(18, 18))
        self._heading_btn.setFixedSize(28, 26)
        self._heading_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        heading_menu = QMenu(self._heading_btn)
        for i in range(1, 7):
            prefix = "#" * i + " "
            icon_size = max(8, 20 - i * 2)
            action = heading_menu.addAction(f"H{i}")
            action.setIcon(self._make_colored_icon("heading", icon_color, icon_size))
            action.triggered.connect(lambda checked=False, p=prefix: self._insert_md(p))
        self._heading_btn.setMenu(heading_menu)
        layout.addWidget(self._heading_btn)
        self._toolbar_buttons.append((self._heading_btn, "heading"))
        self._toolbar_tooltips.append(self.tr("Heading level"))
        _sep()

        # --- Blocks: lists ---
        _btn("list-unordered", "- ", self.tr("Unordered list (- )"))
        _btn("list-ordered", "1. ", self.tr("Ordered list (1. )"))
        _btn("list-task", "- [ ] ", self.tr("Task list (- [ ])"))
        _sep()

        # --- Blocks: other ---
        _btn("quote", "> ", self.tr("Blockquote (> )"))
        _btn("code-block", "```", self.tr("Code block (```)"))
        _btn(
            "table",
            "\n| Col 1 | Col 2 |\n|------|------|\n|      |      |\n",
            self.tr("Insert table"),
        )
        _btn("hr", "---\n", self.tr("Horizontal rule (---)"))
        _sep()

        # --- Inline ---
        _btn("bold", "**", self.tr("Bold (**text**)"))
        _btn("italic", "*", self.tr("Italic (*text*)"))
        _btn("strikethrough", "~~", self.tr("Strikethrough (~~text~~)"))
        _btn("code", "`", self.tr("Inline code (`text`)"))
        _sep()

        # --- Links & media ---
        _btn("link", "[]()", self.tr("Insert link ([]())"))
        _btn("image", "![]()", self.tr("Insert image (![]())"))

        layout.addStretch()
        return tb

    def _recolor_toolbar_icons(self) -> None:
        icon_color = self._current_theme.icon_color
        for button, name in getattr(self, "_toolbar_buttons", []):
            button.setIcon(self._make_colored_icon(name, icon_color))

    def _on_find(self) -> None:
        tab = self._current_tab()
        if isinstance(tab, EditorTab):
            tab.open_find()

    def _on_find_in_files(self) -> None:
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
            self._side_search_btn.setChecked(True)
            self._side_tree_btn.setChecked(False)
            self._side_search_btn.blockSignals(False)
            self._side_tree_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(1)
            self._show_left_panel()
            self._search_input.setFocus()
            self._search_input.selectAll()

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
        cursor = tab.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextBlock,
            QTextCursor.MoveMode.MoveAnchor,
            line_num - 1,
        )
        tab.editor.setTextCursor(cursor)
        tab.editor.centerCursor()

    def _on_editor_context_menu(self, point: QPoint) -> None:
        """Right-click menu on the editor with formatting actions."""
        menu = QMenu(self)
        ic = self._current_theme.icon_color

        inline_menu = menu.addMenu(self.tr("Inline &Formatting"))
        inline_menu.setIcon(self._make_colored_icon("bold", ic))
        inline_menu.addAction(self._make_colored_icon("bold", ic), self.tr("&Bold")).triggered.connect(
            lambda: self._insert_md("**")
        )
        inline_menu.addAction(self._make_colored_icon("italic", ic), self.tr("&Italic")).triggered.connect(
            lambda: self._insert_md("*")
        )
        inline_menu.addAction(self._make_colored_icon("strikethrough", ic), self.tr("&Strikethrough")).triggered.connect(
            lambda: self._insert_md("~~")
        )
        inline_menu.addAction(self._make_colored_icon("code", ic), self.tr("Inline &Code")).triggered.connect(
            lambda: self._insert_md("`")
        )

        lists_menu = menu.addMenu(self.tr("&Lists"))
        lists_menu.setIcon(self._make_colored_icon("list-unordered", ic))
        lists_menu.addAction(self._make_colored_icon("list-unordered", ic), self.tr("&Unordered list")).triggered.connect(
            lambda: self._insert_md("- ")
        )
        lists_menu.addAction(self._make_colored_icon("list-ordered", ic), self.tr("&Ordered list")).triggered.connect(
            lambda: self._insert_md("1. ")
        )
        lists_menu.addAction(self._make_colored_icon("list-task", ic), self.tr("&Task list")).triggered.connect(
            lambda: self._insert_md("- [ ] ")
        )

        blocks_menu = menu.addMenu(self.tr("&Blocks"))
        blocks_menu.setIcon(self._make_colored_icon("quote", ic))
        blocks_menu.addAction(self._make_colored_icon("quote", ic), self.tr("Block&quote")).triggered.connect(
            lambda: self._insert_md("> ")
        )
        blocks_menu.addAction(self._make_colored_icon("code-block", ic), self.tr("Code &block")).triggered.connect(
            lambda: self._insert_md("```")
        )
        blocks_menu.addAction(self._make_colored_icon("table", ic), self.tr("&Table")).triggered.connect(
            lambda: self._insert_md(
                "\n| Col 1 | Col 2 |\n|------|------|\n|      |      |\n"
            )
        )
        blocks_menu.addAction(self._make_colored_icon("hr", ic), self.tr("&Horizontal rule")).triggered.connect(
            lambda: self._insert_md("---\n")
        )

        insert_menu = menu.addMenu(self.tr("&Insert"))
        insert_menu.setIcon(self._make_colored_icon("link", ic))
        insert_menu.addAction(self._make_colored_icon("link", ic), self.tr("&Link")).triggered.connect(
            lambda: self._insert_md("[]()")
        )
        insert_menu.addAction(self._make_colored_icon("image", ic), self.tr("&Image")).triggered.connect(
            lambda: self._insert_md("![]()")
        )

        sender = self.sender()
        if isinstance(sender, QPlainTextEdit):
            menu.exec(sender.viewport().mapToGlobal(point))

    def _insert_md(self, syntax: str) -> None:
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

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _setup_statusbar(self) -> None:
        pass  # inline status bar is created in _setup_central

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
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
        from ui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(
            self._theme_id,
            self._editor_font_family,
            self._editor_font_size,
            self._preview_font_family,
            self._preview_font_size,
            self._language,
            self._line_number_mode,
            self._smart_editing.get("link_style", "md"),
            self._smart_editing,
            self._folder_settings,
            self,
        )
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return

        settings = QSettings("cutemd", "cutemd")

        # --- Theme ---
        new_theme_id = dlg.selected_theme_id()
        if new_theme_id != self._theme_id:
            self._theme_id = new_theme_id
            self._current_theme = (
                system_theme() if new_theme_id == "system" else get_theme(new_theme_id)
            )
            settings.setValue("theme", new_theme_id)
            self._apply_theme()

        # --- Language ---
        new_lang = dlg.selected_language()
        if new_lang != self._language:
            self._language = new_lang
            settings.setValue("language", new_lang)
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
            settings.setValue("editor_font_family", new_ef)
            settings.setValue("editor_font_size", new_efs)
            changed = True

        if new_pf != self._preview_font_family or new_pfs != self._preview_font_size:
            self._preview_font_family = new_pf
            self._preview_font_size = new_pfs
            settings.setValue("preview_font_family", new_pf)
            settings.setValue("preview_font_size", new_pfs)
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
            settings.setValue("line_number_mode", new_ln)
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_line_number_mode(new_ln)

        # --- Smart editing ---
        new_se = dlg.selected_smart_editing()
        new_ls = dlg.selected_link_style()
        new_se["link_style"] = new_ls
        if new_se != self._smart_editing:
            self._smart_editing = new_se
            settings.setValue("smart_editing/enabled", new_se["enabled"])
            settings.setValue("smart_editing/auto_pair", new_se["auto_pair"])
            settings.setValue("smart_editing/auto_pair_brackets", new_se["auto_pair_brackets"])
            settings.setValue("smart_editing/continue_lists", new_se["continue_lists"])
            settings.setValue("smart_editing/backspace_pairs", new_se["backspace_pairs"])
            settings.setValue("link_style", new_ls)
            for i in range(self._tabs.count()):
                tab = self._tabs.widget(i)
                if isinstance(tab, EditorTab):
                    tab.set_smart_editing(new_se)

    def _on_toggle_preview(self, checked: bool) -> None:
        self._preview_visible = checked
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab.set_preview_visible(checked)

    def _on_toggle_tree(self, visible: bool) -> None:
        if visible:
            self._side_tree_btn.blockSignals(True)
            self._side_search_btn.blockSignals(True)
            self._side_tree_btn.setChecked(True)
            self._side_search_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_search_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(0)
            self._show_left_panel()
        else:
            self._side_tree_btn.setChecked(False)
            self._side_search_btn.setChecked(False)
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
        self._folder_path = path
        self._folder_settings = FolderSettings(path)
        self._folder_settings.load()
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._tree_panel.set_root_path(path)
        self._add_recent_folder(path)
        QSettings("cutemd", "cutemd").setValue("last_folder", str(path))
        self._update_menu_state()

    def _restore_last_folder(self) -> None:
        # If launched with file arguments (e.g. "Open with"), open them in edit mode
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

        settings = QSettings("cutemd", "cutemd")
        last = str(settings.value("last_folder", ""))
        if last and Path(last).is_dir():
            self._set_folder(Path(last))
            return

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
        if not folder_mode:
            self._side_tree_btn.blockSignals(True)
            self._side_search_btn.blockSignals(True)
            self._side_tree_btn.setChecked(False)
            self._side_search_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_search_btn.blockSignals(False)
            self._hide_left_panel()
            self.act_toggle_tree.setChecked(False)
            self._side_folder_btn.setText("...")
        else:
            self._side_tree_btn.blockSignals(True)
            self._side_search_btn.blockSignals(True)
            self._side_tree_btn.setChecked(True)
            self._side_search_btn.setChecked(False)
            self._side_tree_btn.blockSignals(False)
            self._side_search_btn.blockSignals(False)
            self._left_stack.setCurrentIndex(0)
            self._show_left_panel()
            self.act_toggle_tree.setChecked(True)
            self._side_folder_btn.setText(self._folder_path.name)
        self._update_window_title()

    def _add_recent_folder(self, path: Path) -> None:
        settings = QSettings("cutemd", "cutemd")
        recent = settings.value("recent_folders", [])
        if isinstance(recent, str):
            recent = [recent] if recent else []
        if not isinstance(recent, list):
            recent = []
        sp = str(path.resolve())
        recent = [p for p in recent if p != sp]
        recent.insert(0, sp)
        settings.setValue("recent_folders", recent[:10])

    def _on_close_folder(self) -> None:
        tab = self._current_tab()
        if tab and not tab.maybe_save():
            return
        self._folder_path = None
        self._folder_settings = None
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._tree_panel.set_root_path("")
        QSettings("cutemd", "cutemd").remove("last_folder")
        self._update_menu_state()

    def _on_tree_file_activated(self, path: str) -> None:
        p = Path(path)
        idx = self._find_tab_for_file(p)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
            return

        tab = self._current_tab()
        # Reuse current tab if it is unmodified (empty or saved file)
        if tab is not None and not tab.is_modified:
            tab.load_file(p)
            self._refresh_tab_title(tab)
            self._update_window_title()
            self._tree_panel.select_file(p)
            return

        # Current tab is modified — open in a new tab
        tab = self._add_tab()
        tab.load_file(p)
        self._refresh_tab_title(tab)
        self._update_window_title()
        self._tree_panel.select_file(p)

    def _on_tree_file_new_tab(self, path: str) -> None:
        """Open *path* in a new tab unconditionally."""
        p = Path(path)
        tab = self._add_tab()
        tab.load_file(p)
        self._refresh_tab_title(tab)
        self._update_window_title()
        self._tree_panel.select_file(p)

    def _on_file_link_clicked(self, source_tab: EditorTab, target: str) -> None:
        """Click on a link/wikilink — open URL in browser or file in a tab."""
        # URLs → open in browser
        if target.startswith(("http://", "https://", "www.")):
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl

            url = target if "://" in target else "https://" + target
            QDesktopServices.openUrl(QUrl(url))
            return

        path = self._resolve_link_target(target, source_tab.file_path)
        if path is None and self._folder_path is not None:
            stem = Path(target).stem.lower()
            for p in self._folder_path.rglob("*.md"):
                if p.stem.lower() == stem:
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
        self.act_toggle_preview.setText(self.tr("Toggle &Preview"))
        self.act_toggle_split.setText(self.tr("Toggle Split &Orientation"))
        self.act_toggle_tree.setText(self.tr("Toggle &File Tree"))
        self.act_toggle_statusbar.setText(self.tr("Toggle Status &Bar"))
        self.act_settings.setText(self.tr("&Settings…"))

        # Menu titles
        self._file_menu.setTitle(self.tr("&File"))
        self._edit_menu.setTitle(self.tr("&Edit"))
        self._view_menu.setTitle(self.tr("&View"))
        self._settings_menu.setTitle(self.tr("&Settings"))
        self._help_menu.setTitle(self.tr("&Help"))

        # Toolbar tooltips
        self._heading_btn.setToolTip(self.tr("Heading level"))
        tips = [
            self.tr("Unordered list (- )"),
            self.tr("Ordered list (1. )"),
            self.tr("Task list (- [ ])"),
            self.tr("Blockquote (> )"),
            self.tr("Code block (```)"),
            self.tr("Insert table"),
            self.tr("Horizontal rule (---)"),
            self.tr("Bold (**text**)"),
            self.tr("Italic (*text*)"),
            self.tr("Strikethrough (~~text~~)"),
            self.tr("Inline code (`text`)"),
            self.tr("Insert link ([]())"),
            self.tr("Insert image (![]())"),
        ]
        for (btn, _), tip in zip(self._toolbar_buttons, tips):
            btn.setToolTip(tip)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._update_window_title()
            self._retranslate_ui()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        for i in range(self._tabs.count() - 1, -1, -1):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and not tab.maybe_save():
                event.ignore()
                return
        QSettings("cutemd", "cutemd").setValue("window_geometry", self.saveGeometry())
        event.accept()

    def sizeHint(self) -> QSize:
        return QSize(1200, 750)
