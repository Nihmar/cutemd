"""Single editor+preview tab for the tabbed interface."""

from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QToolButton,
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
        editor_font_family: str = "System",
        editor_font_size: int = 11,
        preview_font_family: str = "System",
        preview_font_size: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._md = md_parser
        self._preview_css = preview_css
        self._theme = theme

        self._file_path: Path | None = None
        self._saved_text: str = ""
        self._dirty = False
        self._syncing_scroll = 0
        self._last_anchor: str = ""
        self._line_anchor_map: list[int] = []
        self._line_anchor_map_hash: int = 0
        self._pending_sync_anchor: str = ""
        self._sync_retries = 0
        self._preview_visible = True

        self._editor_font_family = editor_font_family
        self._editor_font_size = editor_font_size
        self._preview_font_family = preview_font_family
        self._preview_font_size = preview_font_size

        # --- Editor ---
        self.editor = QPlainTextEdit()
        self._apply_editor_font()
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
        self.preview.verticalScrollBar().valueChanged.connect(self._on_preview_scrolled)

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

        # --- Find bar (hidden by default) ---
        self._find_bar = QWidget(self)
        self._find_bar.setVisible(False)
        self._find_bar.setFixedHeight(30)
        find_layout = QHBoxLayout(self._find_bar)
        find_layout.setContentsMargins(4, 0, 4, 0)
        find_layout.setSpacing(4)

        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText(self.tr("Find…"))
        self._find_input.setMaximumWidth(200)
        self._find_input.setFixedHeight(24)
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._find_input.returnPressed.connect(self._find_next)

        self._find_count_label = QLabel()

        self._find_case_btn = QToolButton()
        self._find_case_btn.setText("Aa")
        self._find_case_btn.setCheckable(True)
        self._find_case_btn.setToolTip(self.tr("Match case"))
        self._find_case_btn.setFixedSize(28, 24)
        self._find_case_btn.toggled.connect(self._highlight_all_matches)

        prev_btn = QToolButton()
        prev_btn.setText("▲")
        prev_btn.setToolTip(self.tr("Previous match"))
        prev_btn.setFixedSize(28, 24)
        prev_btn.clicked.connect(self._find_prev)

        next_btn = QToolButton()
        next_btn.setText("▼")
        next_btn.setToolTip(self.tr("Next match"))
        next_btn.setFixedSize(28, 24)
        next_btn.clicked.connect(self._find_next)

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip(self.tr("Close find bar"))
        close_btn.setFixedSize(28, 24)
        close_btn.clicked.connect(self.close_find)

        find_layout.addWidget(self._find_input)
        find_layout.addWidget(self._find_count_label)
        find_layout.addStretch()
        find_layout.addWidget(self._find_case_btn)
        find_layout.addWidget(prev_btn)
        find_layout.addWidget(next_btn)
        find_layout.addWidget(close_btn)
        layout.addWidget(self._find_bar)

        # Escape closes the find bar
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self._find_bar, self.close_find)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def file_path(self) -> Path | None:
        return self._file_path

    @property
    def is_modified(self) -> bool:
        return self.editor.toPlainText() != self._saved_text

    def display_name(self) -> str:
        """Tab title: file name or 'Untitled' with optional *."""
        name = self._file_path.name if self._file_path else self.tr("Untitled")
        return f"{name} *" if self.is_modified else name

    def tooltip(self) -> str:
        """Full path for the tab tooltip."""
        return str(self._file_path) if self._file_path else self.tr("Untitled")

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

    def set_editor_font(self, family: str, size: int) -> None:
        """Change the editor font family and size."""
        self._editor_font_family = family
        self._editor_font_size = size
        self._apply_editor_font()

    def set_preview_font(self, family: str, size: int) -> None:
        """Change the preview font family and size and re-render."""
        self._preview_font_family = family
        self._preview_font_size = size
        self._update_preview()

    def load_file(self, path: Path) -> None:
        """Load *path* into the editor, replacing current content."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Could not open file:\n{}").format(e),
            )
            return
        self.editor.setPlainText(text)
        self._file_path = path
        self._saved_text = text
        self.title_changed.emit()

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
        if not self.is_modified:
            return True
        name = self._file_path.name if self._file_path else self.tr("Untitled")
        ret = QMessageBox.question(
            self,
            self.tr("Unsaved changes"),
            self.tr('"{}" has been modified.\nSave changes?').format(name),
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
            return not self.is_modified
        return ret != QMessageBox.StandardButton.Cancel

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _apply_editor_font(self) -> None:
        """Apply the configured font to the editor widget."""
        if self._editor_font_family in ("System", "Sistema"):
            font = QFont("monospace", self._editor_font_size)
        else:
            font = QFont(self._editor_font_family, self._editor_font_size)
        self.editor.setFont(font)

    def _write_file(self, path: Path) -> bool:
        try:
            text = self.editor.toPlainText()
            path.write_text(text, encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Could not save file:\n{}").format(e),
            )
            return False
        self._file_path = path
        self._saved_text = text
        self.title_changed.emit()
        return True

    def _check_modified(self) -> None:
        """Emit modified_changed if the dirty state toggled."""
        dirty = self.editor.toPlainText() != self._saved_text
        if dirty != getattr(self, "_dirty", False):
            self._dirty = dirty
            self.modified_changed.emit(dirty)
            self.title_changed.emit()

    def _on_text_changed(self) -> None:
        self._check_modified()
        self._preview_timer.start()
        self._emit_status()
        self._line_anchor_map_hash = 0

    def _emit_status(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        text = self.editor.toPlainText()
        words = len(text.split()) if text else 0
        self.status_changed.emit(
            self.tr("Ln {}, Col {}").format(line, col),
            self.tr("{} words").format(words),
        )

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

        # Inline font style overrides the CSS defaults
        font_style = f"font-size: {self._preview_font_size}px;"
        if self._preview_font_family != "Sistema":
            font_style += f" font-family: {self._preview_font_family};"

        html = (
            "<!DOCTYPE html>\n"
            "<html>\n<head>\n"
            "<meta charset='utf-8'>\n"
            f"<style>\n{self._preview_css}\n</style>\n"
            "</head>\n"
            f"<body class='{theme_class}' style='{font_style}'>\n"
            f"{body_html}\n"
            "</body>\n</html>"
        )

        self._syncing_scroll += 1
        self.preview.setHtml(html)
        self._syncing_scroll -= 1

        self._pending_sync_anchor = self._last_anchor
        self._sync_retries = 0
        self._sync_preview_scroll()

    def _sync_preview_scroll(self) -> None:
        """Scroll the preview to the cached anchor, retrying if layout is not ready.

        Called after setHtml() — the scrollbar may not have its final
        range yet, so we retry on subsequent event-loop ticks up to
        10 times.
        """
        if self._syncing_scroll > 0:
            return
        anchor = self._pending_sync_anchor
        if not anchor:
            return
        preview_sb = self.preview.verticalScrollBar()
        if preview_sb.maximum() > 0:
            self._syncing_scroll += 1
            self.preview.scrollToAnchor(anchor)
            self._syncing_scroll -= 1
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
        if self._syncing_scroll > 0 or not self._preview_visible:
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
        self._syncing_scroll += 1
        self.preview.scrollToAnchor(anchor)
        self._syncing_scroll -= 1

    def _on_preview_scrolled(self, _value: int = 0) -> None:
        """Scroll the editor proportionally to match the preview position."""
        if self._syncing_scroll > 0 or not self._preview_visible:
            return
        preview_sb = self.preview.verticalScrollBar()
        max_pv = preview_sb.maximum()
        if max_pv <= 0:
            return
        editor_sb = self.editor.verticalScrollBar()
        max_ed = editor_sb.maximum()
        if max_ed <= 0:
            return
        ratio = preview_sb.value() / max_pv
        target = int(ratio * max_ed)
        if abs(editor_sb.value() - target) < 5:
            return
        self._syncing_scroll += 1
        editor_sb.setValue(target)
        self._syncing_scroll -= 1

    # ------------------------------------------------------------------
    # Find / search
    # ------------------------------------------------------------------
    def _find_flags(self) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if getattr(self, "_find_case_btn", None) and self._find_case_btn.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def _highlight_all_matches(self, _checked: bool = False) -> None:
        """Highlight all occurrences of the search term."""
        self._highlight_all_matches_impl()
        self._update_count_label()

    def _highlight_all_matches_impl(self) -> None:
        self._clear_highlights()
        term = self._find_input.text()
        if not term:
            return
        doc = self.editor.document()
        flags = self._find_flags()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(255, 255, 0, 100))
        cursor = doc.find(term, 0, flags)
        while not cursor.isNull():
            sel = QTextCursor(cursor)
            sel.movePosition(
                QTextCursor.MoveOperation.Right,
                QTextCursor.MoveMode.KeepAnchor,
                len(term),
            )
            extra_sel = self.editor.ExtraSelection()
            extra_sel.format = fmt
            extra_sel.cursor = sel
            self._find_selections.append(extra_sel)
            cursor = doc.find(term, cursor, flags)
        saved = getattr(self, "_saved_selections", [])
        self.editor.setExtraSelections(self._find_selections + saved)

    def _update_count_label(self) -> None:
        count = len(self._find_selections)
        if count:
            idx = self._find_focused_index()
            if idx >= 0:
                self._find_count_label.setText(
                    f"{idx + 1}/{count}"
                )
            else:
                self._find_count_label.setText(self.tr("{}/{}").format(0, count))
        else:
            self._find_count_label.setText("")

    def _find_focused_index(self) -> int:
        """Return index of the current match if cursor is exactly on one, else -1."""
        cp = self.editor.textCursor().position()
        anchor = self.editor.textCursor().anchor()
        # Only consider if cursor is exactly at a match start or selection
        for i, sel in enumerate(self._find_selections):
            if sel.selectionStart() == anchor and sel.selectionEnd() == cp:
                return i
            if sel.selectionStart() == cp and sel.selectionEnd() == anchor:
                return i
        return -1

    def _clear_highlights(self) -> None:
        self._find_selections = []
        saved = getattr(self, "_saved_selections", [])
        self.editor.setExtraSelections(saved)

    def _on_find_text_changed(self, _text: str) -> None:
        self._highlight_all_matches()
        # Jump to the first match after the cursor
        self._find_next()

    def _find_next(self) -> None:
        term = self._find_input.text()
        if not term:
            return
        flags = self._find_flags()
        found = self.editor.find(term, flags)
        if not found:
            # Wrap around
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(term, flags)
        self._update_count_label()

    def _find_prev(self) -> None:
        term = self._find_input.text()
        if not term:
            return
        flags = self._find_flags() | QTextDocument.FindFlag.FindBackward
        found = self.editor.find(term, flags)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.editor.setTextCursor(cursor)
            self.editor.find(term, flags)
        self._update_count_label()

    def open_find(self) -> None:
        """Show the find bar and focus the input."""
        self._find_bar.setVisible(True)
        self._find_input.setFocus()
        self._find_input.selectAll()
        if self.editor.textCursor().hasSelection():
            self._find_input.setText(self.editor.textCursor().selectedText())
        self._saved_selections = self.editor.extraSelections()
        self._find_selections = []

    def close_find(self) -> None:
        """Hide the find bar and clear highlights."""
        self._find_bar.setVisible(False)
        self._clear_highlights()
        self.editor.setFocus()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.title_changed.emit()
        super().changeEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(800, 600)
