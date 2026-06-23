"""Single editor+preview tab for the tabbed interface."""

import re
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from markdown.html_builder import (
    build_html,
    preprocess_wikilink_images,
    preprocess_wikilinks,
    strip_frontmatter,
)
from ui.find_bar import FindBar
from ui.image_viewer import ImageViewer
from ui.markdown_completer import MarkdownAutoCompleter
from ui.pdf_viewer import PdfViewer
from ui.preview_browser import PreviewTextBrowser, get_image_size
from ui.syntax_highlighter import MarkdownHighlighter

# ---------------------------------------------------------------------------
# LineNumberArea
# ---------------------------------------------------------------------------


class LineNumberArea(QWidget):
    """Widget that paints line numbers alongside the editor.

    Mode values:
        0 — hidden
        1 — every line
        2 — multiples of 5 (plus line 1 and the last line)
    """

    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor)
        self._editor = editor
        self._mode = 1

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        self.update()

    def sizeHint(self) -> QSize:
        if self._mode == 0:
            return QSize(0, 0)
        return QSize(self._line_number_area_width(), 0)

    def _line_number_area_width(self) -> int:
        digits = len(str(max(1, self._editor.blockCount())))
        space = 10 + self._editor.fontMetrics().horizontalAdvance("9") * digits
        return space

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)
        if self._mode == 0:
            return
        painter = QPainter(self)
        painter.fillRect(
            event.rect(),
            QColor(
                self._editor.palette().color(self._editor.palette().ColorRole.Window)
            ),
        )

        block = self._editor.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(
            self._editor.blockBoundingGeometry(block)
            .translated(self._editor.contentOffset())
            .top()
        )
        bottom = top + int(self._editor.blockBoundingRect(block).height())

        fg = self._editor.palette().color(self._editor.palette().ColorRole.Mid)
        painter.setPen(fg)
        painter.setFont(self._editor.font())
        total_blocks = self._editor.blockCount()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = block_num + 1
                if self._mode == 1 or self._should_draw_line(line, total_blocks):
                    number = str(line)
                    painter.drawText(
                        0,
                        top,
                        self.width() - 4,
                        self._editor.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        number,
                    )
                elif self._mode == 2:
                    painter.drawText(
                        0,
                        top,
                        self.width() - 4,
                        self._editor.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        "·",
                    )
            block = block.next()
            top = bottom
            bottom = (
                top + int(self._editor.blockBoundingRect(block).height())
                if block.isValid()
                else top
            )
            block_num += 1

    @staticmethod
    def _should_draw_line(line: int, total: int) -> bool:
        return line == 1 or line == total or line % 5 == 0


# ---------------------------------------------------------------------------
# EditorTab
# ---------------------------------------------------------------------------


class EditorTab(QWidget):
    """A single tab containing an editor pane, a live preview pane, and
    synchronised scrolling between them.

    Signals:
        modified_changed(bool) — fired when the dirty flag toggles.
        status_changed(str, str) — line:col message + language hint.
        title_changed() — tab title needs refresh.
        file_link_clicked(str) — a local markdown/wikilink was clicked.
    """

    modified_changed = Signal(bool)
    status_changed = Signal(str, str)
    title_changed = Signal()
    file_link_clicked = Signal(str)

    _MD_EXTS = frozenset({".md", ".markdown"})
    _IMG_EXTS = frozenset(
        {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}
    )
    _PDF_EXTS = frozenset({".pdf"})

    # -- Link detection in the editor (clickable links + hover underline) --
    _LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    _WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

    def __init__(
        self,
        md_parser: MarkdownIt,
        preview_css: str,
        theme: str,
        editor_font_family: str = "System",
        editor_font_size: int = 11,
        preview_font_family: str = "System",
        preview_font_size: int = 16,
        smart_editing: dict[str, Any] | None = None,
        cursor_width: int = 2,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._md = md_parser
        self._preview_css = preview_css
        self._theme = theme

        self._file_path: Path | None = None
        self._images_dir: Path | None = None
        self._saved_text: str = ""
        self._dirty = False
        self._syncing_scroll = 0
        self._last_anchor: str = ""
        self._line_anchor_map: list[int] = []
        self._line_anchor_map_hash: int = 0
        self._pending_sync_anchor: str = ""
        self._sync_retries = 0
        self._preview_visible = True
        self._current_line_sel: object = None
        self._is_binary_preview = False

        self._hover_link_key: tuple[int, int, int] | None = None

        self._editor_font_family = editor_font_family
        self._editor_font_size = editor_font_size
        self._preview_font_family = preview_font_family
        self._preview_font_size = preview_font_size

        # --- Editor ---
        self.editor = QPlainTextEdit()
        self._apply_editor_font()
        self.editor.setTabStopDistance(40)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setCursorWidth(cursor_width)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._emit_status)

        self._highlighter = MarkdownHighlighter(self.editor.document())
        self._highlighter.set_theme(theme)

        self._line_number_area = LineNumberArea(self.editor)
        self._update_line_number_area_width()
        self.editor.blockCountChanged.connect(self._update_line_number_area_width)
        self.editor.updateRequest.connect(self._update_line_number_area)
        self.editor.cursorPositionChanged.connect(self._on_highlight_current_line)
        self.editor.installEventFilter(self)
        self._viewport = self.editor.viewport()
        self._viewport.setMouseTracking(True)
        self._viewport.installEventFilter(self)
        self._completer = MarkdownAutoCompleter(self.editor, smart_editing, self)

        # --- Preview stack ---
        self.preview = PreviewTextBrowser()
        self.preview.setReadOnly(True)
        self.preview.setOpenLinks(False)
        self.preview.setOpenExternalLinks(False)
        self.preview.file_link_clicked.connect(
            lambda target: self.file_link_clicked.emit(target)
        )
        if self._images_dir is not None:
            self.preview.set_images_dir(self._images_dir)

        self._image_viewer = ImageViewer()
        self._image_viewer.viewport().installEventFilter(self._image_viewer)

        self._pdf_viewer = PdfViewer()
        self._pdf_viewer._scroll.viewport().installEventFilter(self._pdf_viewer)

        self._preview_stack = QStackedWidget()
        self._preview_stack.addWidget(self.preview)
        self._preview_stack.addWidget(self._image_viewer)
        self._preview_stack.addWidget(self._pdf_viewer)
        self._preview_stack.installEventFilter(self)

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
        splitter.addWidget(self._preview_stack)
        splitter.setSizes([500, 500])
        self._splitter = splitter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # --- Find bar ---
        self._find_bar = FindBar(self.editor, self)
        self._find_bar.highlights_changed.connect(self._apply_all_selections)
        self._find_bar.closed.connect(
            lambda: (self._clear_highlights(), self.editor.setFocus())
        )
        layout.addWidget(self._find_bar)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def file_path(self) -> Path | None:
        return self._file_path

    @property
    def is_modified(self) -> bool:
        if self._is_binary_preview:
            return False
        return self.editor.toPlainText() != self._saved_text

    def display_name(self) -> str:
        name = self._file_path.name if self._file_path else self.tr("Untitled")
        return f"{name} *" if self.is_modified else name

    def tooltip(self) -> str:
        return str(self._file_path) if self._file_path else self.tr("Untitled")

    def set_theme(self, theme: str, pygments_style: str = "") -> None:
        if theme != self._theme:
            self._theme = theme
            self._highlighter.set_theme(theme)
            self._update_preview()

    def set_preview_visible(self, visible: bool) -> None:
        if visible == self._preview_visible:
            return
        self._preview_visible = visible
        self._preview_stack.setVisible(visible)
        if visible:
            self._update_preview()

    def set_editor_font(self, family: str, size: int) -> None:
        self._editor_font_family = family
        self._editor_font_size = size
        self._apply_editor_font()

    def set_line_number_mode(self, mode: int) -> None:
        self._line_number_area.set_mode(mode)
        self._update_line_number_area_width()

    def set_smart_editing(self, settings: dict[str, Any]) -> None:
        self._completer.update_settings(settings)

    def set_cursor_width(self, width: int) -> None:
        self.editor.setCursorWidth(width)

    def set_preview_font(self, family: str, size: int) -> None:
        self._preview_font_family = family
        self._preview_font_size = size
        self._update_preview()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def load_file(self, path: Path) -> None:
        ext = path.suffix.lower()
        if ext in self._IMG_EXTS:
            self._file_path = path
            self._load_image(path)
            self.title_changed.emit()
            return
        if ext in self._PDF_EXTS:
            self._file_path = path
            self._load_pdf(path)
            self.title_changed.emit()
            return

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
        self._dirty = False
        self._is_binary_preview = False
        self.editor.setReadOnly(False)
        self._preview_stack.setCurrentIndex(0)
        self._splitter.setSizes([500, 500])
        self.title_changed.emit()

        if ext in self._MD_EXTS:
            self._highlighter.setDocument(self.editor.document())
        else:
            self._highlighter.setDocument(None)

    def _load_image(self, path: Path) -> None:
        self.editor.setPlainText(self.tr("Image preview \u2014 {}").format(path.name))
        self.editor.setReadOnly(True)
        self._highlighter.setDocument(None)
        self._saved_text = ""
        self._image_viewer.load(path)
        self._preview_stack.setCurrentIndex(1)
        self._is_binary_preview = True
        self._splitter.setSizes([0, 1000])

    def _load_pdf(self, path: Path) -> None:
        self.editor.setPlainText(self.tr("PDF \u2014 {}").format(path.name))
        self.editor.setReadOnly(True)
        self._highlighter.setDocument(None)
        self._saved_text = ""
        self._pdf_viewer.load(path)
        self._preview_stack.setCurrentIndex(2)
        self._is_binary_preview = True
        self._splitter.setSizes([0, 1000])

    def save(self) -> bool:
        if self._file_path:
            return self._write_file(self._file_path)
        return False

    def save_as(self, path: Path) -> bool:
        self._file_path = path
        return self._write_file(path)

    def _write_file(self, path: Path) -> bool:
        try:
            path.write_text(self.editor.toPlainText(), encoding="utf-8")
            self._saved_text = self.editor.toPlainText()
            self._dirty = False
            self.editor.document().setModified(False)
            self.modified_changed.emit(False)
            self.title_changed.emit()
            return True
        except OSError as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Could not save file:\n{}").format(e),
            )
            return False

    def maybe_save(self) -> bool:
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
                return False
            return not self.is_modified
        return ret != QMessageBox.StandardButton.Cancel

    # ------------------------------------------------------------------
    # Editor helpers
    # ------------------------------------------------------------------

    def _apply_editor_font(self) -> None:
        font = QFont()
        if self._editor_font_family != "System":
            font.setFamily(self._editor_font_family)
        font.setPointSize(self._editor_font_size)
        self.editor.setFont(font)

    def _update_line_number_area_width(self) -> None:
        self.editor.setViewportMargins(
            self._line_number_area.sizeHint().width(), 0, 0, 0
        )

    def _update_line_number_area(self) -> None:
        self._line_number_area.update()

    def _on_highlight_current_line(self) -> None:
        if self._current_line_sel is not None:
            self._current_line_sel = None
            self._apply_all_selections()

    def _apply_all_selections(self) -> None:
        extra = []
        if self._current_line_sel is not None:
            extra.append(self._current_line_sel)
        extra.extend(self._find_bar.selections)
        self.editor.setExtraSelections(extra)

    def _emit_status(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.status_changed.emit(f"{line}:{col}", "Markdown")

    def _on_text_changed(self) -> None:
        self._preview_timer.start()
        was_dirty = self._dirty
        self._dirty = self.is_modified
        if self._dirty != was_dirty:
            self.modified_changed.emit(self._dirty)

    def set_images_dir(self, d: Path | None) -> None:
        """Set the configured images directory (from folder settings)."""
        self._images_dir = d
        self.preview.set_images_dir(d)

    # ------------------------------------------------------------------
    # Preview rendering
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        if not self._preview_visible or self._is_binary_preview:
            return
        raw_text = self.editor.toPlainText()
        text = strip_frontmatter(raw_text)
        text = preprocess_wikilinks(preprocess_wikilink_images(text))
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

        base_dir = self._file_path.parent if self._file_path else Path.cwd()
        self.preview.set_base_dir(base_dir)
        pw = self.preview.width()

        html = build_html(
            text=text,
            md=self._md,
            preview_css=self._preview_css,
            theme=self._theme,
            font_family=self._preview_font_family,
            font_size=self._preview_font_size,
            base_dir=base_dir,
            max_width=max(pw, 200),
            get_image_size=get_image_size,
            images_dir=self._images_dir,
        )

        self._syncing_scroll += 1
        self.preview.setHtml(html)
        self._syncing_scroll -= 1

        self._pending_sync_anchor = self._last_anchor
        self._sync_retries = 0
        self._sync_preview_scroll()

    def _build_line_anchor_map(self, text: str) -> list[int]:
        from markdown.tools import BLOCK_OPEN_TYPES

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

    # ------------------------------------------------------------------
    # Scroll sync
    # ------------------------------------------------------------------

    def _sync_preview_scroll(self) -> None:
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
        if (
            self._syncing_scroll > 0
            or not self._preview_visible
            or self._is_binary_preview
        ):
            return
        line_map = self._line_anchor_map
        if not line_map:
            return
        first_block = self.editor.firstVisibleBlock()
        current_line = first_block.blockNumber()
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
        if (
            self._syncing_scroll > 0
            or not self._preview_visible
            or self._is_binary_preview
        ):
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
    # Clickable link navigation (hover underline + click to open)
    # ------------------------------------------------------------------

    @classmethod
    def _link_range_at(
        cls, pos_in_block: int, text: str
    ) -> tuple[str, int, int] | None:
        for m in cls._WIKILINK_RE.finditer(text):
            if m.start() <= pos_in_block <= m.end():
                inner = m.group(1).strip()
                target = inner.split("|")[-1].strip() if "|" in inner else inner
                return (target, m.start(), m.end())
        for m in cls._LINK_RE.finditer(text):
            if m.start() <= pos_in_block <= m.end():
                return (m.group(2).strip(), m.start(), m.end())
        return None

    def _on_mouse_move(self, event: QMouseEvent) -> None:
        pt = event.position().toPoint()
        cursor = self.editor.cursorForPosition(pt)
        block = cursor.block()
        block_text = block.text()
        pos = cursor.positionInBlock()
        link = self._link_range_at(pos, block_text)

        if link:
            _target, start, end = link
            new_key = (block.blockNumber(), start, end)
            if new_key == self._hover_link_key:
                return
            self._hover_link_key = new_key

            block_start = block.position()
            sel = QTextCursor(self.editor.document())
            sel.setPosition(block_start + start)
            sel.setPosition(block_start + end, QTextCursor.MoveMode.KeepAnchor)

            fmt = QTextCharFormat()
            fmt.setFontUnderline(True)
            fmt.setUnderlineColor(QColor("#61afef"))
            extra = QTextEdit.ExtraSelection()
            extra.format = fmt
            extra.cursor = sel
            self.editor.setExtraSelections([extra])
            self._viewport.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            if self._hover_link_key is not None:
                self._hover_link_key = None
                self.editor.setExtraSelections([])
                self._viewport.setCursor(Qt.CursorShape.IBeamCursor)

    def _on_mouse_click(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pt = event.position().toPoint()
        cursor = self.editor.cursorForPosition(pt)
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        link = self._link_range_at(pos, block_text)
        if link:
            self.file_link_clicked.emit(link[0])
            return True
        return False

    # ------------------------------------------------------------------
    # Find bar
    # ------------------------------------------------------------------
    def _clear_highlights(self) -> None:
        self._apply_all_selections()

    def open_find(self) -> None:
        self._find_bar.open()

    def close_find(self) -> None:
        self._find_bar.close()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is self.editor:
            if event.type() == QEvent.Type.Resize:
                cr = self.editor.contentsRect()
                self._line_number_area.setGeometry(
                    QRect(
                        cr.left(),
                        cr.top(),
                        self._line_number_area.sizeHint().width(),
                        cr.height(),
                    )
                )
                return super().eventFilter(obj, event)

        elif obj is self._viewport:
            if event.type() == QEvent.Type.MouseMove:
                self._on_mouse_move(event)  # type: ignore[arg-type]
            elif event.type() == QEvent.Type.MouseButtonRelease:
                return self._on_mouse_click(event)  # type: ignore[arg-type]

        elif obj is self._preview_stack and event.type() == QEvent.Type.Resize:
            self._preview_timer.start()

        return super().eventFilter(obj, event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.title_changed.emit()
