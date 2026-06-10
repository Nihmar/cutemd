"""Main window for the Markdown editor."""

from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextCursor,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from markdown.math_renderers import (
    render_math_block,
    render_math_block_label,
    render_math_inline,
    render_math_inline_double,
)
from markdown.tools import highlight_code
from ui import theme
from ui.editor_tab import EditorTab
from ui.file_tree_panel import FileTreePanel
from ui.themes import get_theme, system_theme

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parent.parent
_CSS_PATH = _PROJECT_DIR / "ui" / "preview_styles.css"


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._folder_path: Path | None = None
        self._preview_visible = True

        # Restore saved theme (default: system)
        settings = QSettings("cutemd", "cutemd")
        self._theme_id = str(settings.value("theme", "system"))
        self._current_theme = (
            system_theme() if self._theme_id == "system" else get_theme(self._theme_id)
        )

        # Load custom CSS once
        self._preview_css = _CSS_PATH.read_text() if _CSS_PATH.exists() else ""

        # --- Markdown parser (shared across all tabs) ---
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
        self.act_open_folder = QAction("Open &Folder\u2026", self)
        self.act_open_folder.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open_folder.triggered.connect(self._on_open_folder)

        self.act_close_folder = QAction("Close Folder", self)
        self.act_close_folder.triggered.connect(self._on_close_folder)

        self.act_new = QAction("&New File\u2026", self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self._on_new)

        self.act_save = QAction("&Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._on_save)

        self.act_save_as = QAction("Save &As\u2026", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self._on_save_as)

        self.act_close_tab = QAction("Close Tab", self)
        self.act_close_tab.setShortcut(QKeySequence.StandardKey.Close)
        self.act_close_tab.triggered.connect(self._on_close_tab)

        self.act_exit = QAction("E&xit", self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_exit.triggered.connect(self.close)

        # Edit
        self.act_undo = QAction("&Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)

        self.act_redo = QAction("&Redo", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)

        # View
        self.act_toggle_preview = QAction("Toggle &Preview", self)
        self.act_toggle_preview.setCheckable(True)
        self.act_toggle_preview.setChecked(True)
        self.act_toggle_preview.toggled.connect(self._on_toggle_preview)

        self.act_toggle_split = QAction("Toggle Split &Orientation", self)
        self.act_toggle_split.triggered.connect(self._toggle_split)

        self.act_settings = QAction("&Settings…", self)
        self.act_settings.triggered.connect(self._on_settings)

    # ------------------------------------------------------------------
    # Menubar
    # ------------------------------------------------------------------
    def _setup_menubar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        file_menu.addAction(self.act_open_folder)
        file_menu.addAction(self.act_close_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_close_tab)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        edit_menu = mb.addMenu("&Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)

        view_menu = mb.addMenu("&View")
        view_menu.addAction(self.act_toggle_preview)
        view_menu.addAction(self.act_toggle_split)

        settings_menu = mb.addMenu("&Settings")
        settings_menu.addAction(self.act_settings)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------
    def _setup_central(self) -> None:
        # --- File tree panel (left sidebar) ---
        self._tree_panel = FileTreePanel()
        self._tree_panel.file_activated.connect(self._on_tree_file_activated)
        self._tree_panel.file_open_new_tab.connect(self._on_tree_file_new_tab)

        # --- Tabs ---
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # --- Editor toolbar (acts on the active tab) ---
        editor_toolbar = self._make_editor_toolbar()

        # --- Editor pane (toolbar + tabs) ---
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(editor_toolbar)
        editor_layout.addWidget(self._tabs)

        # Splitter: tree | [toolbar+tabs]
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._tree_panel)
        self._splitter.addWidget(editor_pane)
        self._splitter.setSizes([220, 980])

        self.setCentralWidget(self._splitter)

        # Open with one empty tab
        self._add_tab()

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------
    def _add_tab(self) -> EditorTab:
        tab = EditorTab(
            self._md,
            self._preview_css,
            "dark" if self._current_theme.is_dark else "light",
        )
        tab.modified_changed.connect(self._on_tab_modified)
        tab.status_changed.connect(self._on_tab_status)
        tab.title_changed.connect(lambda: self._refresh_tab_title(tab))

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
        # Connect window-level undo/redo to this tab's editor
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
        path = str(_PROJECT_DIR / "ui" / "icons" / f"{name}.svg")
        renderer = QSvgRenderer(path)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        coloured = QPixmap(size, size)
        coloured.fill(color)
        painter = QPainter(coloured)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_DestinationIn
        )
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return QIcon(coloured)

    def _make_editor_toolbar(self) -> QWidget:
        icon_color = self._current_theme.icon_color
        self._toolbar_buttons: list[tuple[QToolButton, str]] = []

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

        # --- Heading dropdown ---
        heading_combo = QComboBox()
        heading_combo.setToolTip("Heading level")
        heading_combo.addItem("H", "")
        for i in range(1, 7):
            heading_combo.addItem(f"H{i}", "#" * i + " ")
        heading_combo.currentIndexChanged.connect(self._on_heading_combo)
        heading_combo.setFixedWidth(48)
        layout.addWidget(heading_combo)
        _sep()

        # --- Blocks: lists ---
        _btn("list-unordered", "- ", "Unordered list")
        _btn("list-ordered", "1. ", "Ordered list")
        _btn("list-task", "- [ ] ", "Task list")
        _sep()

        # --- Blocks: other ---
        _btn("quote", "> ", "Blockquote")
        _btn("code-block", "```", "Code block")
        _btn(
            "table",
            "\n| Col 1 | Col 2 |\n|------|------|\n|      |      |\n",
            "Insert table",
        )
        _btn("hr", "---\n", "Horizontal rule")
        _sep()

        # --- Inline ---
        _btn("bold", "**", "Bold")
        _btn("italic", "*", "Italic")
        _btn("strikethrough", "~~", "Strikethrough")
        _btn("code", "`", "Inline code")
        _sep()

        # --- Links & media ---
        _btn("link", "[]()", "Insert link")
        _btn("image", "![]()", "Insert image")

        layout.addStretch()
        return tb

    def _recolor_toolbar_icons(self) -> None:
        icon_color = self._current_theme.icon_color
        for button, name in getattr(self, "_toolbar_buttons", []):
            button.setIcon(self._make_colored_icon(name, icon_color))

    def _on_heading_combo(self, index: int) -> None:
        if index <= 0:
            return
        prefix = "#" * index + " "
        self._insert_md(prefix)
        self.sender().setCurrentIndex(0)  # type: ignore[union-attr]

    def _on_editor_context_menu(self, point) -> None:
        """Right-click menu on the editor with formatting actions."""
        menu = QMenu(self)

        menu.addAction("Bold").triggered.connect(lambda: self._insert_md("**"))
        menu.addAction("Italic").triggered.connect(lambda: self._insert_md("*"))
        menu.addAction("Strikethrough").triggered.connect(lambda: self._insert_md("~~"))
        menu.addAction("Inline code").triggered.connect(lambda: self._insert_md("`"))
        menu.addSeparator()
        menu.addAction("Unordered list").triggered.connect(
            lambda: self._insert_md("- ")
        )
        menu.addAction("Ordered list").triggered.connect(lambda: self._insert_md("1. "))
        menu.addAction("Task list").triggered.connect(lambda: self._insert_md("- [ ] "))
        menu.addSeparator()
        menu.addAction("Blockquote").triggered.connect(lambda: self._insert_md("> "))
        menu.addAction("Code block").triggered.connect(lambda: self._insert_md("```"))
        menu.addAction("Table").triggered.connect(
            lambda: self._insert_md(
                "\n| Col 1 | Col 2 |\n|------|------|\n|      |      |\n"
            )
        )
        menu.addAction("Horizontal rule").triggered.connect(
            lambda: self._insert_md("---\n")
        )
        menu.addSeparator()
        menu.addAction("Insert link").triggered.connect(lambda: self._insert_md("[]()"))
        menu.addAction("Insert image").triggered.connect(
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
        self._status_file = QLabel("No folder")
        self._status_cursor = QLabel("Ln 1, Col 1")
        self._status_words = QLabel("0 words")

        bar = self.statusBar()
        bar.addWidget(self._status_file, 1)
        bar.addPermanentWidget(self._status_cursor)
        bar.addPermanentWidget(self._status_words)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        import ui.themes as themes_mod

        themes_mod.PYGMENTS_STYLE = self._current_theme.pygments_style

        pal = self._current_theme.build_palette()
        QApplication.instance().setPalette(pal)  # type: ignore[union-attr]

        # Re-generate QSS with the new palette
        app = QApplication.instance()
        if app:
            app.setStyleSheet(theme.load_qss(pal))  # type: ignore[attr-defined]

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

        dlg = SettingsDialog(self._theme_id, self)
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return

        new_id = dlg.selected_theme_id()
        if new_id == self._theme_id:
            return

        self._theme_id = new_id
        self._current_theme = (
            system_theme() if new_id == "system" else get_theme(new_id)
        )
        QSettings("cutemd", "cutemd").setValue("theme", new_id)
        self._apply_theme()

    def _on_toggle_preview(self, checked: bool) -> None:
        self._preview_visible = checked
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab):
                tab.set_preview_visible(checked)

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
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", "")
        if not folder:
            return
        self._set_folder(Path(folder))

    def _set_folder(self, path: Path) -> None:
        self._folder_path = path
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._tree_panel.set_root_path(path)
        self._update_window_title()
        QSettings("cutemd", "cutemd").setValue("last_folder", str(path))

    def _restore_last_folder(self) -> None:
        settings = QSettings("cutemd", "cutemd")
        last = str(settings.value("last_folder", ""))
        if last and Path(last).is_dir():
            self._set_folder(Path(last))
        else:
            self._on_open_folder()

    def _on_close_folder(self) -> None:
        tab = self._current_tab()
        if tab and not tab.maybe_save():
            return
        self._folder_path = None
        for i in range(self._tabs.count() - 1, -1, -1):
            self._tabs.removeTab(i)
        self._add_tab()
        self._tree_panel.set_root_path("")
        self._update_window_title()
        QSettings("cutemd", "cutemd").remove("last_folder")

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
                self._status_file.setText(self._folder_path.name)
        else:
            self._status_file.setText("No folder")

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        for i in range(self._tabs.count() - 1, -1, -1):
            tab = self._tabs.widget(i)
            if isinstance(tab, EditorTab) and not tab.maybe_save():
                event.ignore()
                return
        event.accept()

    def sizeHint(self) -> QSize:
        return QSize(1200, 750)
