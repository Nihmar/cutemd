"""Main window for the Markdown editor."""

import re
from pathlib import Path

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
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
# Markdown → HTML helpers
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
# MainWindow
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._file_path: str | None = None
        self._modified = False
        self._theme = "dark"
        self._syncing_scroll = False  # guard against scroll feedback loops
        self._last_anchor: str | None = None  # track section changes

        # Load custom CSS once
        self._preview_css = _CSS_PATH.read_text() if _CSS_PATH.exists() else ""

        # --- Markdown parser ---
        self._md = MarkdownIt("commonmark", {"highlight": _highlight_code}).enable(
            ["table", "strikethrough"]
        )

        # --- UI ---
        self.setWindowTitle("CuteMD – Markdown Editor")
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

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _setup_actions(self) -> None:
        # File
        self.act_new = QAction("&New", self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self._on_new)

        self.act_open = QAction("&Open…", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self._on_open)

        self.act_save = QAction("&Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._on_save)

        self.act_save_as = QAction("Save &As…", self)
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

        # Synchronized scrolling (editor → preview only)
        self._editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)

        # Splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._editor)
        self._splitter.addWidget(self._preview)
        self._splitter.setSizes([600, 600])

        self.setCentralWidget(self._splitter)

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
        self.setWindowTitle(f"{name}{mod} – CuteMD")
        self._status_file.setText(self._file_path or "New file")

    # ------------------------------------------------------------------
    # Editor signals
    # ------------------------------------------------------------------
    def _on_text_changed(self) -> None:
        self._modified = True
        self._update_title()
        self._preview_timer.start()  # debounced
        self._update_status()

    def _update_status(self) -> None:
        cursor = self._editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self._status_cursor.setText(f"Ln {line}, Col {col}")

        text = self._editor.toPlainText()
        word_count = len(text.split()) if text else 0
        self._status_words.setText(f"{word_count} words")

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _update_preview(self) -> None:
        text = self._editor.toPlainText()
        try:
            body_html = _add_heading_ids(self._md.render(text))
        except Exception:
            # Fallback: escape HTML and show as plain preformatted text
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

    # ------------------------------------------------------------------
    # Synchronized scrolling (editor to preview)
    # ------------------------------------------------------------------
    def _on_editor_scrolled(self, _value: int) -> None:
        if self._syncing_scroll:
            return

        editor_sb = self._editor.verticalScrollBar()
        preview_sb = self._preview.verticalScrollBar()
        editor_max = editor_sb.maximum()
        preview_max = preview_sb.maximum()
        if editor_max <= 0 or preview_max <= 0:
            return

        # Same percentage through both panes.
        fraction = editor_sb.value() / editor_max
        self._syncing_scroll = True
        preview_sb.setValue(int(preview_max * fraction))
        self._syncing_scroll = False

    def _find_current_anchor(self) -> str | None:
        """Return the slug of the nearest heading at or above the first
        visible line, or None if no heading is found."""
        block = self._editor.firstVisibleBlock()
        for _ in range(200):  # limit backward search
            match = _HEADING_LINE_RE.match(block.text())
            if match:
                return _slugify(match.group(1))
            block = block.previous()
            if not block.isValid():
                break
        return None

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
