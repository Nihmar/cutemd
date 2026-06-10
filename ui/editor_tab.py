"""Single editor+preview tab for the tabbed interface."""

from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from markdown.tools import BLOCK_OPEN_TYPES, add_heading_ids
from ui.syntax_highlighter import MarkdownHighlighter


class EditorTab(QWidget):
    """A single tab containing an editor pane, a live preview pane, and
    synchronised scrolling between them.

    Signals:
        modified_changed(bool)   — emitted when the dirty flag toggles.
        status_changed(str, str) — cursor position and word count.
        title_changed()          — emitted so the tab bar can refresh.
    """

    modified_changed = Signal(bool)
    status_changed = Signal(str, str)
    title_changed = Signal()

    def __init__(
        self,
        md_parser: MarkdownIt,
        preview_css: str,
        theme: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._md = md_parser
        self._preview_css = preview_css
        self._theme = theme

        self._file_path: Path | None = None
        self._modified = False
        self._syncing_scroll = False
        self._last_anchor: str = ""
        self._line_anchor_map: list[int] = []
        self._line_anchor_map_hash: int = 0
        self._pending_sync_anchor: str = ""
        self._sync_retries = 0
        self._preview_visible = True

        # --- Editor ---
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("monospace", 11))
        self.editor.setTabStopDistance(40)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._emit_status)

        self._highlighter = MarkdownHighlighter(self.editor.document())
        self._highlighter.set_theme(theme)  # type: ignore[attr-defined]

        # --- Preview ---
        self.preview = QTextBrowser()
        self.preview.setReadOnly(True)
        self.preview.setOpenExternalLinks(True)

        # --- Scroll sync ---
        self.editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)

        # --- Debounce timer ---
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

        # --- Layout ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.preview)
        splitter.setSizes([500, 500])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def file_path(self) -> Path | None:
        return self._file_path

    @property
    def is_modified(self) -> bool:
        return self._modified

    def display_name(self) -> str:
        """Tab title: file name or 'Untitled' with optional *."""
        name = self._file_path.name if self._file_path else "Untitled"
        return f"{name} *" if self._modified else name

    def tooltip(self) -> str:
        """Full path for the tab tooltip."""
        return str(self._file_path) if self._file_path else "Untitled"

    def set_theme(self, theme: str, pygments_style: str = "") -> None:
        """Update highlighter theme and re-render preview."""
        if theme != self._theme:
            self._theme = theme
            self._highlighter.set_theme(theme)  # type: ignore[attr-defined]
            self._update_preview()
        # Pygments style for code blocks — updated via global in highlight_code

    def set_preview_visible(self, visible: bool) -> None:
        """Show or hide the preview pane."""
        if visible == self._preview_visible:
            return
        self._preview_visible = visible
        self.preview.setVisible(visible)
        if visible:
            self._update_preview()

    def load_file(self, path: Path) -> None:
        """Load *path* into the editor, replacing current content."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")
            return
        self.editor.setPlainText(text)
        self._file_path = path
        self._set_modified(False)

    def save(self) -> bool:
        """Save to the current path.  Returns True on success."""
        if self._file_path:
            return self._write_file(self._file_path)
        return False

    def save_as(self, path: Path) -> bool:
        """Save to *path*.  Returns True on success."""
        return self._write_file(path)

    def maybe_save(self) -> bool:
        """Ask to save if modified.  Returns False if user cancels."""
        if not self._modified:
            return True
        name = self._file_path.name if self._file_path else "Untitled"
        ret = QMessageBox.question(
            self,
            "Unsaved changes",
            f'"{name}" has been modified.\nSave changes?',
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Save:
            if self._file_path:
                self._write_file(self._file_path)
            else:
                # The caller should handle Save As for untitled files
                return False
            return not self._modified
        return ret != QMessageBox.StandardButton.Cancel

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _write_file(self, path: Path) -> bool:
        try:
            path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            return False
        self._file_path = path
        self._set_modified(False)
        return True

    def _set_modified(self, value: bool) -> None:
        if value != self._modified:
            self._modified = value
            self.modified_changed.emit(value)
            self.title_changed.emit()

    def _on_text_changed(self) -> None:
        self._set_modified(True)
        self._preview_timer.start()
        self._emit_status()
        self._line_anchor_map_hash = 0

    def _emit_status(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        text = self.editor.toPlainText()
        words = len(text.split()) if text else 0
        self.status_changed.emit(f"Ln {line}, Col {col}", f"{words} words")

    # ------------------------------------------------------------------
    # Preview & scroll sync
    # ------------------------------------------------------------------
    def _render_with_anchors(self, text: str) -> str:
        """Render HTML with <a name='bN'> anchors at each block start.

        Anchors are used by scrollToAnchor() in the scroll-sync logic
        to keep the preview in exact lockstep with the editor viewport.
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
        """Return a per-line array that maps editor line number → anchor index.

        For each source line we pick the narrowest (most specific)
        block-level token that contains it, so list items and
        multi-paragraph blocks resolve to the correct anchor.
        """
        tokens = self._md.parse(text)
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
                mapping[line] = last_anchor
                for s, e, aidx in entries:
                    if line < s:
                        mapping[line] = aidx
                        break
        return mapping

    def _update_preview(self) -> None:
        if not self._preview_visible:
            return
        text = self.editor.toPlainText()
        text_hash = hash(text)
        if text_hash != self._line_anchor_map_hash:
            self._line_anchor_map = self._build_line_anchor_map(text)
            self._line_anchor_map_hash = text_hash

        first_block = self.editor.firstVisibleBlock()
        current_line = first_block.blockNumber()
        line_map = self._line_anchor_map
        current_anchor_idx = (
            line_map[current_line] if current_line < len(line_map) else 0
        )
        self._last_anchor = f"b{current_anchor_idx}"

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
        self.preview.setHtml(html)
        self._syncing_scroll = False

        self._pending_sync_anchor = self._last_anchor
        self._sync_retries = 0
        self._sync_preview_scroll()

    def _sync_preview_scroll(self) -> None:
        """Scroll the preview to the cached anchor, retrying if layout is not ready.

        Called after setHtml() — the scrollbar may not have its final
        range yet, so we retry on subsequent event-loop ticks up to
        10 times.
        """
        if self._syncing_scroll:
            return
        anchor = self._pending_sync_anchor
        if not anchor:
            return
        preview_sb = self.preview.verticalScrollBar()
        if preview_sb.maximum() > 0:
            self._syncing_scroll = True
            self.preview.scrollToAnchor(anchor)
            self._syncing_scroll = False
            self._pending_sync_anchor = ""
        else:
            if self._sync_retries < 10:
                self._sync_retries += 1
                QTimer.singleShot(0, self._sync_preview_scroll)
            else:
                self._pending_sync_anchor = ""
                self._sync_retries = 0

    def _on_editor_scrolled(self, _value: int = 0) -> None:
        """Scroll the preview to match the block at the top of the editor.

        Uses the cached line→anchor map to find which anchor corresponds
        to the first visible line in the editor, then calls
        scrollToAnchor() on the preview.
        """
        if self._syncing_scroll or not self._preview_visible:
            return
        line_map = self._line_anchor_map
        if not line_map:
            return
        first_block = self.editor.firstVisibleBlock()
        current_line = first_block.blockNumber()
        if current_line >= len(line_map):
            return
        anchor_idx = line_map[current_line]
        anchor = f"b{anchor_idx}"
        if anchor == self._last_anchor:
            return
        self._last_anchor = anchor
        preview_sb = self.preview.verticalScrollBar()
        if preview_sb.maximum() <= 0:
            return
        self._syncing_scroll = True
        self.preview.scrollToAnchor(anchor)
        self._syncing_scroll = False

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def sizeHint(self) -> QSize:
        return QSize(800, 600)
