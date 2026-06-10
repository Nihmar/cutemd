"""Main window for the Markdown editor."""

import re
from pathlib import Path

from latex2mathml.converter import convert as _tex2mathml
from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QToolBar,
)

from syntax_highlighter import MarkdownHighlighter

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parent
_CSS_PATH = _PROJECT_DIR / "preview_styles.css"

# Module-level Pygments style name, updated by MainWindow._apply_theme()
_PYGMENTS_STYLE: str = "monokai"


# ---------------------------------------------------------------------------
# Math -> MathML renderers for dollarmath plugin
# ---------------------------------------------------------------------------
def _render_math_inline(tokens, idx, options, env):
    """Render inline math $...$ as MathML."""
    content = tokens[idx].content
    try:
        return _tex2mathml(content, display="inline")
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<span class="math-inline">${escaped}$</span>'


def _render_math_inline_double(tokens, idx, options, env):
    """Render inline double math $$...$$ as MathML."""
    content = tokens[idx].content
    try:
        return _tex2mathml(content, display="inline")
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<span class="math-inline">$${escaped}$$</span>'


def _render_math_block(tokens, idx, options, env):
    """Render display math $$...$$ as a MathML block."""
    content = tokens[idx].content.strip()
    try:
        mathml = _tex2mathml(content, display="block")
        return f'<div class="math-block">{mathml}</div>'
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<pre class="math-block">$$\n{escaped}\n$$</pre>'


def _render_math_block_label(tokens, idx, options, env):
    """Render labeled display math as a MathML block."""
    content = tokens[idx].content.strip()
    try:
        mathml = _tex2mathml(content, display="block")
        return f'<div class="math-block">{mathml}</div>'
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<pre class="math-block">$$\n{escaped}\n$$</pre>'


# ---------------------------------------------------------------------------
# Themes (QPalette)
# ---------------------------------------------------------------------------
def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.WindowText, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Text, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    p.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    return p


def _light_palette() -> QPalette:
    """Return the default (light) system palette."""
    return QApplication.style().standardPalette()


# ---------------------------------------------------------------------------
# Markdown -> HTML helpers
# ---------------------------------------------------------------------------
def _highlight_code(code: str, lang: str, _attrs: str) -> str:
    """markdown-it-py highlight callback using Pygments with inline styles."""
    lexer = None
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except ClassNotFound:
            pass
    if lexer is None:
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            lexer = get_lexer_by_name("text", stripall=True)

    formatter = HtmlFormatter(style=_PYGMENTS_STYLE, noclasses=True, nowrap=True)
    return highlight(code, lexer, formatter)


def _slugify(text: str) -> str:
    """Generate an HTML anchor slug from heading text."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


_HEADING_TAG_RE = re.compile(r"<(h[1-6])>(.*?)</\1>", re.DOTALL)


def _add_heading_ids(html: str) -> str:
    """Post-process HTML to add id attributes on heading tags."""

    def _replacer(m: re.Match) -> str:
        tag = m.group(1)
        inner = m.group(2)
        plain = re.sub(r"<[^>]+>", "", inner)
        return f'<{tag} id="{_slugify(plain)}">{inner}</{tag}>'

    return _HEADING_TAG_RE.sub(_replacer, html)


_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+(.+)$")


# ---------------------------------------------------------------------------
# Token types that start a visible block-level element in the rendered HTML.
# We inject an <a name='bN'> anchor before each of these so the preview can
# be scrolled to the exact corresponding content.
# ---------------------------------------------------------------------------
_BLOCK_OPEN_TYPES = frozenset(
    {
        "heading_open",
        "paragraph_open",
        "fence",
        "blockquote_open",
        "bullet_list_open",
        "ordered_list_open",
        "table_open",
        "hr",
        "math_block",
        "math_block_label",
        "html_block",
    }
)


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._file_path: str | None = None
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
            MarkdownIt("commonmark", {"highlight": _highlight_code})
            .enable(["table", "strikethrough"])
            .use(dollarmath_plugin)
        )
        # Override math token renderers to produce MathML (instead of raw spans)
        self._md.renderer.rules["math_inline"] = _render_math_inline  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_inline_double"] = _render_math_inline_double  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block"] = _render_math_block  # pyright: ignore[reportAttributeAccessIssue]
        self._md.renderer.rules["math_block_label"] = _render_math_block_label  # pyright: ignore[reportAttributeAccessIssue]

        # --- UI ---
        self.setWindowTitle("CuteMD - Markdown Editor")
        self.resize(1200, 750)

        self._setup_actions()
        self._setup_menubar()
        self._setup_central()
        self._setup_toolbar()
        self._setup_statusbar()
        self._apply_theme()

        # Debounce timer for preview updates
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _setup_actions(self) -> None:
        # File
        self.act_new = QAction("&New", self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self._on_new)

        self.act_open = QAction("&Open...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self._on_open)

        self.act_save = QAction("&Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._on_save)

        self.act_save_as = QAction("Save &As...", self)
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
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
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

        # Preview
        self._preview = QTextBrowser()
        self._preview.setReadOnly(True)
        self._preview.setOpenExternalLinks(True)

        # Synchronized scrolling (editor -> preview only)
        self._editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)

        # Splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._editor)
        self._splitter.addWidget(self._preview)
        self._splitter.setSizes([600, 600])

        self.setCentralWidget(self._splitter)

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------
    def _setup_toolbar(self) -> None:
        tb = QToolBar("Formatting", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        def _add(label: str, syntax: str, tip: str) -> None:
            act = QAction(label, self)
            act.setToolTip(tip)
            act.triggered.connect(lambda checked, s=syntax: self._insert_md(s))
            tb.addAction(act)

        # --- Headings ---
        _add("H1", "# ", "Heading level 1")
        _add("H2", "## ", "Heading level 2")
        _add("H3", "### ", "Heading level 3")
        tb.addSeparator()

        # --- Inline formatting ---
        _add("B", "**", "Bold")
        _add("I", "*", "Italic")
        _add("S", "~~", "Strikethrough")
        _add("`", "`", "Inline code")
        tb.addSeparator()

        # --- Lists ---
        _add("\u2022", "- ", "Unordered list")
        _add("1.", "1. ", "Ordered list")
        _add("\u2610", "- [ ] ", "Task list")
        tb.addSeparator()

        # --- Block elements ---
        _add("```", "```", "Code block")
        _add(">", "> ", "Blockquote")
        _add("\u2014", "---\n", "Horizontal rule")
        tb.addSeparator()

        # --- Links & media ---
        _add("Link", "[]()", "Insert link")
        _add("Img", "![]()", "Insert image")

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
        self._status_file = QLabel("New file")
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
        global _PYGMENTS_STYLE
        if self._theme == "dark":
            QApplication.instance().setPalette(_dark_palette())  # type: ignore[union-attr]
            _PYGMENTS_STYLE = "monokai"
        else:
            QApplication.instance().setPalette(_light_palette())  # type: ignore[union-attr]
            _PYGMENTS_STYLE = "default"

        self._highlighter.set_theme(self._theme)
        self._update_preview()

    def _toggle_theme(self) -> None:
        self._theme = "light" if self._theme == "dark" else "dark"
        self._apply_theme()

    # ------------------------------------------------------------------
    # Split orientation
    # ------------------------------------------------------------------
    def _toggle_split(self) -> None:
        if self._splitter.orientation() == Qt.Orientation.Horizontal:
            self._splitter.setOrientation(Qt.Orientation.Vertical)
        else:
            self._splitter.setOrientation(Qt.Orientation.Horizontal)

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

    def _on_new(self) -> None:
        if not self._maybe_save():
            return
        self._editor.clear()
        self._file_path = None
        self._modified = False
        self._update_title()
        self._update_status()

    def _on_open(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Markdown file",
            "",
            "Markdown files (*.md *.markdown);;All files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")
            return
        self._editor.setPlainText(text)
        self._file_path = path
        self._modified = False
        self._update_title()
        self._update_status()

    def _on_save(self) -> None:
        if self._file_path:
            self._write_file(self._file_path)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Markdown file",
            "",
            "Markdown files (*.md *.markdown);;All files (*)",
        )
        if not path:
            return
        self._write_file(path)

    def _write_file(self, path: str) -> None:
        try:
            Path(path).write_text(self._editor.toPlainText(), encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            return
        self._file_path = path
        self._modified = False
        self._update_title()

    def _update_title(self) -> None:
        name = Path(self._file_path).name if self._file_path else "Untitled"
        mod = " *" if self._modified else ""
        self.setWindowTitle(f"{name}{mod} - CuteMD")
        self._status_file.setText(self._file_path or "New file")

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
            if token.type in _BLOCK_OPEN_TYPES and token.map:
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
            if token.type in _BLOCK_OPEN_TYPES and token.map:
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
            body_html = _add_heading_ids(self._render_with_anchors(text))
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
