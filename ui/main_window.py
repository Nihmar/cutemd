"""Main window for the Markdown editor."""

from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin
from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
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
from markdown.tools import BLOCK_OPEN_TYPES, add_heading_ids, highlight_code
from ui import theme
from ui.file_tree_panel import FileTreePanel
from ui.syntax_highlighter import MarkdownHighlighter

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parent
_CSS_PATH = _PROJECT_DIR / "preview_styles.css"


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._folder_path: Path | None = None
        self._current_file: Path | None = None
        self._modified = False
        self._theme = "dark"
        self._syncing_scroll = False  # guard against scroll feedback loops
        self._last_anchor: str = ""  # track the last anchor name scrolled to
        self._line_anchor_map: list[int] = []  # line->anchor_idx cache
        self._line_anchor_map_hash: int = 0  # cache validity key

        # Load custom CSS once
        self._preview_css = _CSS_PATH.read_text() if _CSS_PATH.exists() else ""

        # --- Markdown parser (with dollarmath plugin for $...$ / $$...$$) ---
        self._md = (
            MarkdownIt("commonmark", {"highlight": highlight_code})
            .enable(["table", "strikethrough"])
            .use(dollarmath_plugin)
        )
        # Override math token renderers to produce MathML (instead of raw spans)
        self._md.renderer.rules["math_inline"] = render_math_inline  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_inline_double"] = render_math_inline_double  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block"] = render_math_block  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block_label"] = render_math_block_label  # pyright: ignore[reportAttributeAccessIssue]

        # --- UI ---
        self.setWindowTitle("CuteMD - Markdown Editor")
        self.resize(1200, 750)

        self._setup_actions()
        self._setup_menubar()
        self._setup_central()
        self._setup_statusbar()
        self._apply_theme()

        # Debounce timer for preview updates
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

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

        self.act_exit = QAction("E&xit", self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_exit.triggered.connect(self.close)

        # Edit
        self.act_undo = QAction("&Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)

        self.act_redo = QAction("&Redo", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)

        # View
        self.act_toggle_split = QAction("Toggle Split &Orientation", self)
        self.act_toggle_split.triggered.connect(self._toggle_split)

        self.act_toggle_theme = QAction("Toggle &Dark/Light Theme", self)
        self.act_toggle_theme.triggered.connect(self._toggle_theme)

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
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        edit_menu = mb.addMenu("&Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)

        view_menu = mb.addMenu("&View")
        view_menu.addAction(self.act_toggle_split)
        view_menu.addAction(self.act_toggle_theme)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------
    def _setup_central(self) -> None:
        # --- File tree panel (left sidebar) ---
        self._tree_panel = FileTreePanel()
        self._tree_panel.file_activated.connect(self._on_tree_file_activated)

        # --- Editor ---
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("monospace", 11))
        self._editor.setTabStopDistance(40)  # 4 spaces
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.cursorPositionChanged.connect(self._update_status)

        # Syntax highlighter
        self._highlighter = MarkdownHighlighter(self._editor.document())
        self._highlighter.set_theme(self._theme)

        # Connect undo/redo to editor
        self.act_undo.triggered.connect(self._editor.undo)
        self.act_redo.triggered.connect(self._editor.redo)

        # --- Editor toolbar (above the editor only) ---
        editor_toolbar = self._make_editor_toolbar()

        # --- Editor pane (toolbar + editor) ---
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(editor_toolbar)
        editor_layout.addWidget(self._editor)

        # --- Preview ---
        self._preview = QTextBrowser()
        self._preview.setReadOnly(True)
        self._preview.setOpenExternalLinks(True)

        # Synchronized scrolling (editor -> preview only)
        self._editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)

        # Splitter: tree | [editor+toolbar | preview]
        inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        inner_splitter.addWidget(editor_pane)
        inner_splitter.addWidget(self._preview)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._tree_panel)
        self._splitter.addWidget(inner_splitter)
        self._splitter.setSizes([220, 980])

        self.setCentralWidget(self._splitter)

    # ------------------------------------------------------------------
    # Editor toolbar
    # ------------------------------------------------------------------
    def _make_editor_toolbar(self) -> QWidget:
        """Return a compact toolbar widget for the editor pane."""
        tb = QWidget()
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        def _btn(text: str, syntax: str, tip: str) -> None:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(lambda checked=False, s=syntax: self._insert_md(s))
            layout.addWidget(b)

        def _sep() -> None:
            s = QWidget()
            s.setFixedWidth(6)
            layout.addWidget(s)

        # --- Heading dropdown ---
        heading_combo = QComboBox()
        heading_combo.setToolTip("Heading level")
        heading_combo.addItem("Heading", "")
        for i in range(1, 7):
            heading_combo.addItem(f"H{i}", "#" * i + " ")
        heading_combo.currentIndexChanged.connect(self._on_heading_combo)
        heading_combo.setFixedWidth(80)
        layout.addWidget(heading_combo)
        _sep()

        # --- Blocks: lists ---
        _btn("\u2022", "- ", "Unordered list")
        _btn("1.", "1. ", "Ordered list")
        _btn("\u2610", "- [ ] ", "Task list")
        _sep()

        # --- Blocks: other ---
        _btn(">", "> ", "Blockquote")
        _btn("```", "```", "Code block")
        _btn(
            "\u2639",
            "\n| Col 1 | Col 2 |\n|------|------|\n|      |      |\n",
            "Insert table",
        )
        _btn("\u2014", "---\n", "Horizontal rule")
        _sep()

        # --- Inline ---
        _btn("B", "**", "Bold")
        _btn("I", "*", "Italic")
        _btn("S", "~~", "Strikethrough")
        _btn("`", "`", "Inline code")
        _sep()

        # --- Links & media ---
        _btn("Link", "[]()", "Insert link")
        _btn("Img", "![]()", "Insert image")

        layout.addStretch()
        return tb

    def _on_heading_combo(self, index: int) -> None:
        """Handle heading dropdown selection."""
        if index <= 0:
            return
        prefix = "#" * index + " "
        self._insert_md(prefix)
        # Reset to placeholder so the same level can be re-selected
        self.sender().setCurrentIndex(0)  # type: ignore[union-attr]

    def _insert_md(self, syntax: str) -> None:
        """Insert markdown syntax at cursor position.

        Behaviour depends on the syntax type:
        - Wrapping syntax (**, *, ~~, `) wraps the selection or inserts
          paired markers with the cursor placed between them.
        - Code block (```) inserts a fenced code block and places the
          cursor on the blank line inside it.
        - Link/Image syntax inserts the template and positions the cursor
          between the brackets.
        - Everything else (prefix syntax like headings, lists, blockquote,
          horizontal rule) inserts at the start of the current line.
        """
        cursor = self._editor.textCursor()

        # --- Wrapping syntax ---
        if syntax in ("**", "*", "~~", "`"):
            sel = cursor.selectedText()
            cursor.insertText(f"{syntax}{sel}{syntax}")
            if not sel:
                # Place cursor between the markers
                cursor.movePosition(
                    QTextCursor.MoveOperation.Left,
                    QTextCursor.MoveMode.MoveAnchor,
                    len(syntax),
                )
                self._editor.setTextCursor(cursor)

        # --- Code block (fenced) ---
        elif syntax == "```":
            cursor.beginEditBlock()
            prefix = "" if cursor.atBlockStart() else "\n"
            cursor.insertText(f"{prefix}```\n\n```")
            # Place cursor on the blank line between the fences
            cursor.movePosition(
                QTextCursor.MoveOperation.PreviousBlock,
                QTextCursor.MoveMode.MoveAnchor,
            )
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.MoveAnchor,
            )
            cursor.endEditBlock()
            self._editor.setTextCursor(cursor)

        # --- Link / Image template ---
        elif syntax in ("[]()", "![]()"):
            cursor.insertText(syntax)
            # Place cursor between the square brackets
            cursor.movePosition(
                QTextCursor.MoveOperation.Left,
                QTextCursor.MoveMode.MoveAnchor,
                len(syntax) - 1,
            )
            self._editor.setTextCursor(cursor)

        # --- Prefix-style (headings, lists, blockquote, HR, etc.) ---
        else:
            if not cursor.atBlockStart():
                cursor.movePosition(
                    QTextCursor.MoveOperation.StartOfBlock,
                    QTextCursor.MoveMode.MoveAnchor,
                )
            cursor.insertText(syntax)

        self._editor.setFocus()

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
        if self._theme == "dark":
            QApplication.instance().setPalette(theme.dark_palette())  # type: ignore[union-attr]
            theme.PYGMENTS_STYLE = "monokai"
        else:
            QApplication.instance().setPalette(theme.light_palette())  # type: ignore[union-attr]
            theme.PYGMENTS_STYLE = "default"

        self._highlighter.set_theme(self._theme)
        self._update_preview()

    def _toggle_theme(self) -> None:
        self._theme = "light" if self._theme == "dark" else "dark"
        self._apply_theme()

    # ------------------------------------------------------------------
    # Split orientation
    # ------------------------------------------------------------------
    def _toggle_split(self) -> None:
        # Find the inner splitter (editor|preview) - it's the last child
        inner = self._splitter.widget(1)
        if isinstance(inner, QSplitter):
            cur = inner.orientation()
            inner.setOrientation(
                Qt.Orientation.Vertical
                if cur == Qt.Orientation.Horizontal
                else Qt.Orientation.Horizontal
            )

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def _maybe_save(self) -> bool:
        """Ask to save unsaved changes.  Returns False if user cancels."""
        if not self._modified:
            return True
        ret = QMessageBox.question(
            self,
            "Unsaved changes",
            "The document has been modified.\nSave changes?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._modified  # False if save was cancelled
        return ret != QMessageBox.StandardButton.Cancel

    def _load_file(self, path: Path) -> None:
        """Load the file at *path* into the editor."""
        if not self._maybe_save():
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")
            return
        self._editor.setPlainText(text)
        self._current_file = path
        self._modified = False
        self._update_title()
        self._update_status()
        self._tree_panel.select_file(path)

    def _on_open_folder(self) -> None:
        """Open a folder and populate the file tree."""
        if not self._maybe_save():
            return
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", "")
        if not folder:
            return
        self._set_folder(Path(folder))

    def _set_folder(self, path: Path) -> None:
        """Set *path* as the working folder."""
        self._folder_path = path
        self._current_file = None
        self._editor.clear()
        self._modified = False
        self._tree_panel.set_root_path(path)
        self._update_title()
        self._update_status()
        # Persist the folder path
        QSettings("cutemd", "cutemd").setValue("last_folder", str(path))

    def _restore_last_folder(self) -> None:
        """On startup, reopen the last folder or prompt for one."""
        settings = QSettings("cutemd", "cutemd")
        last = str(settings.value("last_folder", ""))
        if last and Path(last).is_dir():
            self._set_folder(Path(last))
        else:
            self._on_open_folder()

    def _on_close_folder(self) -> None:
        """Close the current folder."""
        if not self._maybe_save():
            return
        self._folder_path = None
        self._current_file = None
        self._editor.clear()
        self._modified = False
        self._tree_panel.set_root_path("")
        self._update_title()
        self._update_status()
        QSettings("cutemd", "cutemd").remove("last_folder")

    def _on_tree_file_activated(self, path: str) -> None:
        """Handle a file being activated in the tree panel."""
        self._load_file(Path(path))

    def _on_new(self) -> None:
        """Create a new markdown file in the current folder."""
        if not self._folder_path:
            # No folder open - just clear the editor
            if not self._maybe_save():
                return
            self._current_file = None
            self._editor.clear()
            self._modified = False
            self._update_title()
            self._update_status()
            return

        if not self._maybe_save():
            return

        # Pick a unique name
        base = self._folder_path
        i = 1
        while (base / f"untitled_{i}.md").exists():
            i += 1
        new_path = base / f"untitled_{i}.md"

        try:
            new_path.write_text("", encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not create file:\n{e}")
            return

        self._editor.clear()
        self._current_file = new_path
        self._modified = False
        self._update_title()
        self._update_status()
        self._tree_panel.select_file(new_path)

    def _on_save(self) -> None:
        if self._current_file:
            self._write_file(self._current_file)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        start_dir = str(self._folder_path) if self._folder_path else ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown file",
            start_dir,
            "Markdown files (*.md *.markdown);;All files (*)",
        )
        if not path:
            return
        self._write_file(Path(path))

    def _write_file(self, path: Path) -> None:
        try:
            path.write_text(self._editor.toPlainText(), encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            return
        self._current_file = path
        self._modified = False
        self._update_title()
        self._tree_panel.select_file(path)

    def _update_title(self) -> None:
        if self._current_file:
            if self._folder_path:
                try:
                    rel = self._current_file.relative_to(self._folder_path)
                    display = str(rel)
                except ValueError:
                    display = self._current_file.name
            else:
                display = self._current_file.name
        else:
            display = "Untitled"
        mod = " *" if self._modified else ""
        self.setWindowTitle(f"{display}{mod} \u2013 CuteMD")

        # Status bar
        if self._folder_path:
            if self._current_file:
                try:
                    rel = self._current_file.relative_to(self._folder_path)
                    self._status_file.setText(str(rel))
                except ValueError:
                    self._status_file.setText(str(self._current_file))
            else:
                self._status_file.setText(self._folder_path.name)
        else:
            self._status_file.setText("No folder")

    # ------------------------------------------------------------------
    # Editor signals
    # ------------------------------------------------------------------
    def _on_text_changed(self) -> None:
        self._modified = True
        self._update_title()
        self._preview_timer.start()  # debounced
        self._update_status()
        # Invalidate line->anchor cache
        self._line_anchor_map_hash = 0

    def _update_status(self) -> None:
        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self._status_cursor.setText(f"Ln {line}, Col {col}")

        text = self._editor.toPlainText()
        word_count = len(text.split()) if text else 0
        self._status_words.setText(f"{word_count} words")

    # ------------------------------------------------------------------
    # Preview (anchor-based scroll sync)
    # ------------------------------------------------------------------
    def _render_with_anchors(self, text: str) -> str:
        """Render markdown to HTML with <a name='bN'> anchors at block starts.

        Uses the markdown-it token stream to inject anchors immediately
        before each block-level element.  This makes scrollToAnchor()
        exact: the preview scrolls to the same content visible in the
        editor.
        """
        tokens = self._md.parse(text)
        new_tokens: list[Token] = []
        anchor_idx = 0

        for token in tokens:
            if token.type in BLOCK_OPEN_TYPES and token.map:
                start, end = token.map
                if start < end:
                    anchor = Token("html_inline", "", 0)
                    anchor.content = f'<a name="b{anchor_idx}"></a>'
                    new_tokens.append(anchor)
                    anchor_idx += 1
            new_tokens.append(token)

        return self._md.renderer.render(new_tokens, self._md.options, {})

    def _build_line_anchor_map(self, text: str) -> list[int]:
        """Return per-line mapping: index -> anchor index.

        For each line in the source we pick the most specific (narrowest
        map range) block-level token that contains it.  This ensures list
        items and multi-paragraph sections each map to the right anchor.
        """
        tokens = self._md.parse(text)

        # Collect (start_line, end_line, anchor_idx)
        entries: list[tuple[int, int, int]] = []
        anchor_idx = 0
        for token in tokens:
            if token.type in BLOCK_OPEN_TYPES and token.map:
                start, end = token.map
                if start < end:
                    entries.append((start, end, anchor_idx))
                    anchor_idx += 1

        total_lines = len(text.split("\n"))
        mapping = [0] * max(total_lines, 1)
        last_anchor = anchor_idx - 1 if anchor_idx > 0 else 0

        # Sort entries by start line so we can break early
        entries.sort(key=lambda x: x[0])

        for line in range(total_lines):
            best: int | None = None
            best_width = float("inf")
            for start, end, aidx in entries:
                if line < start:
                    break
                if start <= line < end:
                    width = end - start
                    if width < best_width:
                        best_width = width
                        best = aidx
            if best is not None:
                mapping[line] = best
            else:
                # Blank line: use the next visible block's anchor
                mapping[line] = last_anchor
                for s, e, aidx in entries:
                    if line < s:
                        mapping[line] = aidx
                        break

        return mapping

    def _update_preview(self) -> None:
        text = self._editor.toPlainText()

        # --- Build / refresh the line->anchor cache ---
        text_hash = hash(text)
        if text_hash != self._line_anchor_map_hash:
            self._line_anchor_map = self._build_line_anchor_map(text)
            self._line_anchor_map_hash = text_hash

        # Determine which anchor the editor viewport is currently showing
        first_block = self._editor.firstVisibleBlock()
        current_line = first_block.blockNumber()
        line_map = self._line_anchor_map
        current_anchor_idx = (
            line_map[current_line] if current_line < len(line_map) else 0
        )
        self._last_anchor = f"b{current_anchor_idx}"

        # --- Render HTML with anchors ---
        try:
            body_html = add_heading_ids(self._render_with_anchors(text))
        except Exception:
            body_html = (
                "<pre>"
                + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                + "</pre>"
            )

        theme_class = "dark" if self._theme == "dark" else "light"
        html = (
            "<!DOCTYPE html>\n"
            "<html>\n<head>\n"
            "<meta charset='utf-8'>\n"
            f"<style>\n{self._preview_css}\n</style>\n"
            "</head>\n"
            f"<body class='{theme_class}'>\n"
            f"{body_html}\n"
            "</body>\n</html>"
        )

        self._syncing_scroll = True
        self._preview.setHtml(html)
        self._syncing_scroll = False

        # Scroll preview to the saved anchor (with retry if layout isn't
        # ready yet).
        self._pending_sync_anchor = self._last_anchor
        self._sync_retries = 0
        self._sync_preview_scroll()

    def _sync_preview_scroll(self) -> None:
        """Scroll the preview to the pending anchor (with retry logic).

        Called after setHtml() while the layout may not be laid out yet.
        """
        if self._syncing_scroll:
            return

        anchor = getattr(self, "_pending_sync_anchor", "")
        if not anchor:
            return

        preview_sb = self._preview.verticalScrollBar()
        if preview_sb.maximum() > 0:
            self._syncing_scroll = True
            self._preview.scrollToAnchor(anchor)
            self._syncing_scroll = False
            self._pending_sync_anchor = ""
        else:
            retries = getattr(self, "_sync_retries", 0)
            if retries < 10:
                self._sync_retries = retries + 1
                QTimer.singleShot(0, self._sync_preview_scroll)
            else:
                self._pending_sync_anchor = ""
                self._sync_retries = 0

    # ------------------------------------------------------------------
    # Synchronized scrolling (editor -> preview)
    # ------------------------------------------------------------------
    def _on_editor_scrolled(self, _value: int = 0) -> None:
        """Scroll the preview to the anchor matching the editor viewport.

        Uses the line->anchor cache to find which logical block is at the
        top of the editor, then calls scrollToAnchor() on the preview.
        This provides exact content-based sync regardless of how
        differently the two panes render the same content.
        """
        if self._syncing_scroll:
            return

        line_map = self._line_anchor_map
        if not line_map:
            return

        first_block = self._editor.firstVisibleBlock()
        current_line = first_block.blockNumber()
        if current_line >= len(line_map):
            return

        anchor_idx = line_map[current_line]
        anchor = f"b{anchor_idx}"

        # Avoid redundant scrollToAnchor calls when already on the same
        # block (significantly reduces flicker on large documents).
        if anchor == self._last_anchor:
            return
        self._last_anchor = anchor

        preview_sb = self._preview.verticalScrollBar()
        if preview_sb.maximum() <= 0:
            return

        self._syncing_scroll = True
        self._preview.scrollToAnchor(anchor)
        self._syncing_scroll = False

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        if self._maybe_save():
            event.accept()
        else:
            event.ignore()

    def sizeHint(self) -> QSize:
        return QSize(1200, 750)
