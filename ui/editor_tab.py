"""Single editor+preview tab for the tabbed interface."""

import re
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from markdown.document_renderers import (
    cbz_to_html,
    docx_to_html,
    epub_to_html,
    pptx_to_html,
    xlsx_to_html,
)
from markdown.html_builder import (
    preprocess_wikilink_images,
    preprocess_wikilinks,
    strip_frontmatter,
)
from ui.animation_speed import animation_duration_ms
from ui.find_bar import FindBar
from ui.image_viewer import ImageViewer
from ui.link_preview_popup import LinkPreviewPopup
from ui.markdown_completer import MarkdownAutoCompleter
from ui.pdf_viewer import PdfViewer
from ui.preview_browser import PreviewTextBrowser, get_image_size
from ui.preview_worker import PreviewWorker
from ui.syntax_highlighter import MarkdownHighlighter
from core.logging import setup_logging

_LARGE_FILE_THRESHOLD = 1_048_576  # 1 MB

_LOG = setup_logging("cutemd.editor_tab")


def _read_file_with_encoding(path: Path) -> tuple[str | None, str]:
    """Read a file trying multiple encodings. Returns (text, encoding) or
    (None, error_message)."""
    try:
        return path.read_text(encoding="utf-8"), "utf-8"
    except (UnicodeDecodeError, UnicodeError):
        pass
    for enc in ("utf-8-sig", "cp1252", "iso-8859-1", "latin-1", "ascii"):
        try:
            return path.read_text(encoding=enc), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    try:
        raw = path.read_bytes()
        return raw.decode("utf-8", errors="replace"), "utf-8 (broken)"
    except OSError as e:
        return None, str(e)


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
    encoding_changed = Signal(str)

    _MD_EXTS = frozenset({".md", ".markdown"})
    _IMG_EXTS = frozenset(
        {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}
    )
    _PDF_EXTS = frozenset({".pdf"})
    _DOC_EXTS = frozenset({".docx", ".xlsx", ".pptx", ".cbz", ".epub"})

    # -- Link detection in the editor (clickable links + hover underline) --
    _LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    _WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")

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
        self._attachments_dir: Path | None = None
        self._saved_text: str = ""
        self._dirty = False
        self._syncing_scroll = 0
        self._last_anchor: str = ""
        self._line_anchor_map: list[int] = []
        self._line_anchor_map_hash: int = 0
        self._last_rendered_hash: int = 0
        self._pending_render_hash: int = 0
        self._pending_sync_anchor: str = ""
        self._sync_retries = 0
        self._preview_visible = True
        self._current_line_sel: object = None
        self._is_binary_preview = False
        self._file_encoding: str = "utf-8"
        self._large_file = False
        self._link_style: str = "md"
        self._drag_active = False
        self._mouse_press_pos: QPoint | None = None

        # Async preview state.
        self._preview_busy = False
        self._preview_pending = False

        self._hover_link_key: tuple[int, int, int] | None = None
        self._hovered_link_target: str | None = None
        self._broken_link_selections: list[QTextEdit.ExtraSelection] = []

        # --- Link preview popup ---
        self._link_preview_popup = LinkPreviewPopup(self)
        self._link_preview_show_timer = QTimer(self)
        self._link_preview_show_timer.setSingleShot(True)
        self._link_preview_show_timer.setInterval(400)
        self._link_preview_show_timer.timeout.connect(self._on_link_preview_show)

        self._editor_font_family = editor_font_family
        self._editor_font_size = editor_font_size
        self._preview_font_family = preview_font_family
        self._preview_font_size = preview_font_size

        # --- Editor ---
        self.editor = QPlainTextEdit()
        self.editor.setAcceptDrops(True)

        # Timer must exist before textChanged is connected (may fire
        # synchronously during setPlainText).
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

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
        self._link_style = (smart_editing or {}).get("link_style", "md")

        # --- Preview stack ---
        self.preview = PreviewTextBrowser()
        self.preview.setReadOnly(True)
        self.preview.setOpenLinks(False)
        self.preview.setOpenExternalLinks(False)
        self.preview.file_link_clicked.connect(
            lambda target: self.file_link_clicked.emit(target)
        )
        if self._attachments_dir is not None:
            self.preview.set_attachments_dir(self._attachments_dir)
        self._preview_viewport = self.preview.viewport()
        self._preview_viewport.installEventFilter(self)

        self._image_viewer = ImageViewer()
        self._image_viewer.viewport().installEventFilter(self._image_viewer)

        self._pdf_viewer = PdfViewer()
        self._pdf_viewer._scroll.viewport().installEventFilter(self._pdf_viewer)

        self._preview_stack = QStackedWidget()
        self._preview_stack.addWidget(self.preview)  # 0
        self._preview_stack.addWidget(self._image_viewer)  # 1
        self._preview_stack.addWidget(self._pdf_viewer)  # 2

        # Loading spinner (index 3).
        self._loading_label = QLabel()
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setText(self.tr("Rendering\u2026"))
        self._preview_stack.addWidget(self._loading_label)  # 3
        self._preview_stack.installEventFilter(self)

        # --- Scroll sync ---
        self.editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)
        self.preview.verticalScrollBar().valueChanged.connect(self._on_preview_scrolled)

        # --- Async preview worker ---
        self._preview_thread = QThread(self)
        self._preview_worker = PreviewWorker()
        self._preview_worker.moveToThread(self._preview_thread)
        self._preview_worker.result_ready.connect(self._on_preview_ready)
        self._preview_thread.start()

        # --- Layout ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self._preview_stack)
        splitter.setSizes([500, 500])
        self._splitter = splitter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Find bar (top) ---
        self._find_bar = FindBar(self.editor, self)
        self._find_bar.highlights_changed.connect(self._apply_all_selections)
        self._find_bar.closed.connect(
            lambda: (self._clear_highlights(), self.editor.setFocus())
        )
        layout.addWidget(self._find_bar)

        layout.addWidget(splitter)

        _LOG.debug("EditorTab created")

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
            self._last_rendered_hash = 0
            self._highlighter.set_theme(theme)
            self._link_preview_popup.set_theme(theme)
            self._update_preview()

    def set_preview_visible(self, visible: bool) -> None:
        _LOG.debug("set_preview_visible: %s", visible)
        if visible == self._preview_visible:
            return
        self._preview_visible = visible

        total = self._splitter.width()
        if total <= 0:
            self._preview_stack.setVisible(visible)
            if visible:
                self._splitter.setSizes([total // 2, total // 2])
                self._update_preview()
            else:
                self._splitter.setSizes([total, 0])
            return

        # Animate the splitter slide.
        if hasattr(self, "_splitter_anim"):
            self._splitter_anim.stop()
        start_sizes = self._splitter.sizes()
        end_editor = total if not visible else total // 2

        self._splitter.setUpdatesEnabled(False)

        self._splitter_anim = QVariantAnimation(self)
        self._splitter_anim.setDuration(animation_duration_ms(150))
        self._splitter_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._splitter_anim.setStartValue(0.0)
        self._splitter_anim.setEndValue(1.0)

        def _step(progress: float) -> None:
            e = int(start_sizes[0] + (end_editor - start_sizes[0]) * progress)
            self._splitter.setSizes([max(e, 0), max(total - e, 0)])

        self._splitter_anim.valueChanged.connect(_step)

        def _done() -> None:
            self._splitter.setUpdatesEnabled(True)
            if visible:
                self._update_preview()
            else:
                self._preview_stack.setVisible(False)

        self._splitter_anim.finished.connect(_done)

        if visible:
            self._preview_stack.setVisible(True)
        self._splitter_anim.start()

    def set_editor_font(self, family: str, size: int) -> None:
        self._editor_font_family = family
        self._editor_font_size = size
        self._apply_editor_font()

    def set_line_number_mode(self, mode: int) -> None:
        self._line_number_area.set_mode(mode)
        self._update_line_number_area_width()

    def set_smart_editing(self, settings: dict[str, Any]) -> None:
        self._completer.update_settings(settings)
        self._link_style = settings.get("link_style", self._link_style)

    def set_cursor_width(self, width: int) -> None:
        self.editor.setCursorWidth(width)

    def set_preview_font(self, family: str, size: int) -> None:
        self._preview_font_family = family
        self._preview_font_size = size
        self._last_rendered_hash = 0
        self._update_preview()

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    _ZOOM_STEP = 1
    _ZOOM_MIN = 6
    _ZOOM_MAX = 40

    def zoom_editor(self, delta: int) -> None:
        """Zoom the editor font by *delta* points (+1/-1)."""
        new_size = max(self._ZOOM_MIN, min(self._ZOOM_MAX, self._editor_font_size + delta))
        if new_size == self._editor_font_size:
            return
        self._editor_font_size = new_size
        self._apply_editor_font()

    def zoom_preview(self, delta: int) -> None:
        """Zoom the preview font by *delta* points (+1/-1)."""
        new_size = max(self._ZOOM_MIN, min(self._ZOOM_MAX, self._preview_font_size + delta))
        if new_size == self._preview_font_size:
            return
        self._preview_font_size = new_size
        self._last_rendered_hash = 0
        self._update_preview()

    def editor_font_size(self) -> int:
        return self._editor_font_size

    def preview_font_size(self) -> int:
        return self._preview_font_size

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def load_file(self, path: Path) -> None:
        _LOG.debug("load_file: %s", path)
        self._last_rendered_hash = 0
        ext = path.suffix.lower()
        _LOG.debug("load_file: ext=%s _DOC_EXTS=%s hit=%s", ext, self._DOC_EXTS, ext in self._DOC_EXTS)
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
        if ext in self._DOC_EXTS:
            self._file_path = path
            self._load_document(path)
            return

        text, encoding = _read_file_with_encoding(path)
        if text is None:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr("Could not open file:\n{}").format(encoding),
            )
            return

        self._saved_text = text
        self._file_path = path
        self._file_encoding = encoding
        _LOG.debug("load_file: size=%d encoding=%s", len(text), encoding)
        self.editor.setPlainText(text)
        self._dirty = False
        self._is_binary_preview = False
        self.editor.setReadOnly(False)
        self._preview_stack.setCurrentIndex(0)
        self._splitter.setSizes([500, 500])
        self.title_changed.emit()
        self.encoding_changed.emit(encoding)

        if ext in self._MD_EXTS:
            self._highlighter.setDocument(self.editor.document())
        else:
            self._highlighter.setDocument(None)

        # Detect large file and disable expensive features
        self._large_file = path.stat().st_size > _LARGE_FILE_THRESHOLD
        if self._large_file:
            self._highlighter.setDocument(None)
            self._preview_stack.setCurrentIndex(0)

        self._refresh_link_highlights()

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

    def _load_document(self, path: Path) -> None:
        """Render a DOCX / XLSX / PPTX / CBZ / EPUB file as HTML in the preview pane."""
        ext = path.suffix.lower()
        name_map = {".docx": "Word", ".xlsx": "Excel", ".pptx": "PowerPoint", ".cbz": "CBZ", ".epub": "EPUB"}
        label = name_map.get(ext, "Document")
        _LOG.debug("_load_document: %s (%s) label=%s", path.name, ext, label)

        self.editor.setPlainText(self.tr("{} \u2014 {}").format(label, path.name))
        self.editor.setReadOnly(True)
        self._highlighter.setDocument(None)
        self._saved_text = ""
        self._is_binary_preview = True
        self._splitter.setSizes([0, 1000])
        self.title_changed.emit()

        try:
            if ext == ".xlsx":
                html = xlsx_to_html(path, self._preview_css)
            elif ext == ".docx":
                html = docx_to_html(path, self._preview_css)
            elif ext == ".pptx":
                html = pptx_to_html(path, self._preview_css)
            elif ext == ".cbz":
                html = cbz_to_html(path, self._preview_css)
            elif ext == ".epub":
                html = epub_to_html(path, self._preview_css)
            else:
                self.preview.setPlainText(self.tr("[Unsupported document format]"))
                self._preview_stack.setCurrentIndex(0)
                return
            self.preview.setHtml(html)
            self._preview_stack.setCurrentIndex(0)
        except Exception as e:
            _LOG.debug("_load_document: error rendering %s: %s", label, e)
            self.preview.setPlainText(self.tr("[Error rendering {}]").format(label))
            self._preview_stack.setCurrentIndex(0)
            return

        self._refresh_link_highlights()

    def save(self) -> bool:
        _LOG.debug("save: %s", self.file_path)
        if self._file_path:
            return self._write_file(self._file_path)
        return False

    def save_as(self, path: Path) -> bool:
        _LOG.debug("save_as: %s", path)
        self._file_path = path
        return self._write_file(path)

    def _write_file(self, path: Path) -> bool:
        _LOG.debug("_write_file: %s encoding=utf-8", path)
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

    def auto_save(self) -> bool:
        """Silently save if the file has a path and is modified.
        Returns True if actually saved."""
        if (
            not self._is_binary_preview
            and self.is_modified
            and self._file_path is not None
        ):
            try:
                self._file_path.write_text(self.editor.toPlainText(), encoding="utf-8")
                self._saved_text = self.editor.toPlainText()
                self._dirty = False
                self.editor.document().setModified(False)
                self.modified_changed.emit(False)
                self.title_changed.emit()
                return True
            except OSError:
                pass
        return False

    def maybe_save(self) -> bool:
        if not self.is_modified:
            return True
        name = self._file_path.name if self._file_path else self.tr("Untitled")
        _LOG.debug("maybe_save: prompting for %s", self.file_path)
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
        extra.extend(self._broken_link_selections)
        self.editor.setExtraSelections(extra)

    def _emit_status(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        if self._large_file:
            words = self.tr("{} words (large file)").format(
                len(self.editor.toPlainText().split())
            )
        else:
            words = self.tr("{} words").format(
                len(self.editor.toPlainText().split())
            )
        self.status_changed.emit(f"{line}:{col}", words)

    def _on_text_changed(self) -> None:
        _LOG.debug("_on_text_changed")
        # Large files: disable preview and skip expensive work.
        if self._large_file:
            return
        # Debounce adattivo: 150 ms per file piccoli, 500 per file grandi.
        lines = self.editor.document().blockCount()
        self._preview_timer.setInterval(150 if lines < 2000 else 500)
        self._preview_timer.start()
        _LOG.debug("_on_text_changed: debounce=%dms", 150 if lines < 2000 else 500)
        was_dirty = self._dirty
        self._dirty = self.is_modified
        if self._dirty != was_dirty:
            self.modified_changed.emit(self._dirty)

    def set_attachments_dir(self, d: Path | None) -> None:
        """Set the configured images directory (from folder settings)."""
        if d != self._attachments_dir:
            self._last_rendered_hash = 0
        self._attachments_dir = d
        self.preview.set_attachments_dir(d)
        self._refresh_link_highlights()

    # ------------------------------------------------------------------
    # Preview rendering
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        """Render the current Markdown content to HTML in the preview pane.

        Uses adaptive debounce: short delay (150 ms) for small files,
        longer (500 ms) for large files (>20 KB). Tracks pending renders
        via ``_preview_busy`` / ``_preview_pending`` flags to avoid
        unnecessary re-renders when typing quickly. Hash-based change
        detection prevents re-rendering identical content.
        """
        if not self._preview_visible or self._is_binary_preview or self._large_file:
            return
        raw_text = self.editor.toPlainText()
        text = strip_frontmatter(raw_text)
        text = preprocess_wikilinks(preprocess_wikilink_images(text))
        text_hash = hash(text)
        _LOG.debug("_update_preview: hash=%s", text_hash)
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

        # Skip render if nothing meaningful changed.
        pw = self.preview.width()
        params_hash = hash(
            (
                text,
                self._preview_css,
                self._theme,
                self._preview_font_family,
                self._preview_font_size,
                str(base_dir),
                max(pw, 200),
                str(self._attachments_dir) if self._attachments_dir else "",
            )
        )
        if params_hash == self._last_rendered_hash:
            return
        self._pending_render_hash = params_hash

        # Collect render params.
        params: dict[str, Any] = {
            "text": text,
            "md": self._md,
            "preview_css": self._preview_css,
            "theme": self._theme,
            "font_family": self._preview_font_family,
            "font_size": self._preview_font_size,
            "base_dir": base_dir,
            "max_width": max(pw, 200),
            "get_image_size": get_image_size,
            "attachments_dir": self._attachments_dir,
        }

        if self._preview_busy:
            _LOG.debug("_update_preview: debounce skipped (busy)")
            self._preview_pending = True
            self._pending_preview_params = params
            return

        self._preview_busy = True
        # Delay spinner — fast renders don't need it.
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setSingleShot(True)
        self._spinner_timer.timeout.connect(
            lambda: self._preview_stack.setCurrentIndex(3)
        )
        self._spinner_timer.start(100)
        _LOG.debug("_update_preview: rendering %d bytes", len(text))
        self._preview_worker.render_requested.emit(params)
        self._refresh_link_highlights()

    def _on_preview_ready(self, html: str) -> None:
        self._preview_busy = False
        # Cancel spinner if it hasn't fired yet.
        if hasattr(self, "_spinner_timer"):
            self._spinner_timer.stop()

        self._syncing_scroll += 1
        self._preview_stack.setCurrentIndex(0)  # back to preview
        self.preview.setHtml(html)
        self._syncing_scroll -= 1

        # Track rendered state to skip redundant future renders.
        if not self._preview_pending:
            self._last_rendered_hash = self._pending_render_hash

        self._pending_sync_anchor = self._last_anchor
        self._sync_retries = 0
        self._sync_preview_scroll()

        if self._preview_pending:
            self._preview_pending = False
            params = self._pending_preview_params
            self._preview_busy = True
            self._preview_worker.render_requested.emit(params)

    def _build_line_anchor_map(self, text: str) -> list[int]:
        """Build a mapping from editor line numbers to preview heading anchors.

        Parses the markdown-it token stream to find headings, then for each
        editor line determines which heading's anchor should be the scroll
        target. For lines between headings, uses the nearest heading above.
        Used by ``_do_preview_scrolled()`` for reverse scroll synchronization.
        """
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
                # Line is between blocks — use anchor of the nearest block
                # before it, not after it, to avoid the preview jumping ahead.
                prev: int = last_anchor
                for s, e, aidx in entries:
                    if line < s:
                        break
                    prev = aidx
                mapping[line] = prev
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
        # Hide link preview when scrolling.
        self._link_preview_popup.hide()
        self._hovered_link_target = None
        self._link_preview_show_timer.stop()

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
        try:
            self._do_preview_scrolled()
        except Exception:
            import traceback
            traceback.print_exc()
            self._syncing_scroll = 0

    def _do_preview_scrolled(self) -> None:
        """Reverse scroll sync: map the preview's scroll position back to an editor line.

        Uses ``_build_line_anchor_map()`` to convert the current anchor to
        a line number. Falls back to a ratio-based estimate using the
        ``scrollRatio`` callback if no anchor mapping is available.
        """
        if (
            self._syncing_scroll > 0
            or not self._preview_visible
            or self._is_binary_preview
        ):
            return

        # Find which anchor is at the top of the preview viewport.
        # Scan the first few characters of every block starting from the
        # one at the viewport top and moving backward.
        doc = self.preview.document()
        cursor = self.preview.cursorForPosition(QPoint(2, 2))
        block = cursor.block()
        anchor_name = ""
        for _ in range(5):  # check up to 5 blocks backward
            if not block.isValid():
                break
            block_pos = block.position()
            for offset in range(10):
                check_pos = block_pos + offset
                if check_pos >= doc.characterCount():
                    break
                temp = QTextCursor(doc)
                temp.setPosition(check_pos)
                for name in temp.charFormat().anchorNames():
                    if name.startswith("b"):
                        anchor_name = name
                        break
                if anchor_name:
                    break
            if anchor_name:
                break
            block = block.previous()
        if not anchor_name:
            return
        anchor_idx = int(anchor_name[1:])

        # Reverse map: anchor index → first editor line with that anchor
        line_map = self._line_anchor_map
        target_line: int | None = None
        for line, aidx in enumerate(line_map):
            if aidx == anchor_idx:
                target_line = line
                break

        if target_line is None:
            return

        # Scroll editor so that line is near the top.
        # Use a ratio-based approach: line / total_lines.
        editor_sb = self.editor.verticalScrollBar()
        max_ed = editor_sb.maximum()
        if max_ed <= 0:
            return
        total_lines = self.editor.document().blockCount()
        ratio = target_line / max(total_lines - 1, 1)
        self._syncing_scroll += 1
        editor_sb.setValue(int(ratio * max_ed))
        self._syncing_scroll -= 1

    # ------------------------------------------------------------------
    # Clickable link navigation (hover underline + click to open)
    # ------------------------------------------------------------------

    @classmethod
    def _link_range_at(
        cls, pos_in_block: int, text: str
    ) -> tuple[str, int, int] | None:
        for m in cls._WIKILINK_RE.finditer(text):
            if m.start() <= pos_in_block < m.end():
                inner = m.group(1).strip()
                target = inner.split("|")[-1].strip() if "|" in inner else inner
                return (target, m.start(), m.end())
        for m in cls._LINK_RE.finditer(text):
            if m.start() <= pos_in_block < m.end():
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
            _LOG.debug("_on_mouse_move: url link detected")
            target, start, end = link
            new_key = (block.blockNumber(), start, end)
            if new_key != self._hover_link_key:
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

            # --- Link preview popup ---
            # Only restart the timer when the hovered link target changes.
            if target != self._hovered_link_target:
                self._hovered_link_target = target
                self._link_preview_show_timer.start()
        else:
            if self._hover_link_key is not None:
                self._hover_link_key = None
                self.editor.setExtraSelections([])
                self._viewport.setCursor(Qt.CursorShape.IBeamCursor)
            # --- Hide popup when leaving link ---
            if self._hovered_link_target is not None:
                self._hovered_link_target = None
                self._link_preview_show_timer.stop()
                self._link_preview_popup.hide_popup()

    def _on_mouse_click(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Ignore if this was a drag (press and release at different positions).
        if self._mouse_press_pos is not None:
            release_pt = event.position().toPoint()
            if (release_pt - self._mouse_press_pos).manhattanLength() > 5:
                self._mouse_press_pos = None
                return False
        self._mouse_press_pos = None

        pt = event.position().toPoint()
        cursor = self.editor.cursorForPosition(pt)
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        link = self._link_range_at(pos, block_text)
        if link:
            # Hide the link preview popup when clicking a link.
            self._link_preview_popup.hide()
            self._hovered_link_target = None
            self._link_preview_show_timer.stop()
            self.file_link_clicked.emit(link[0])
            return True
        return False

    # ------------------------------------------------------------------
    # Link preview popup
    # ------------------------------------------------------------------

    def _on_link_preview_show(self) -> None:
        """Timer callback: resolve the hovered link and show the popup."""
        target = self._hovered_link_target
        if target is None:
            return

        path = self._resolve_link_target(target)
        if path is None:
            return

        # Compute screen position: below the mouse cursor with a small offset.
        from PySide6.QtGui import QCursor

        global_cursor = QCursor.pos()
        global_pos = QPoint(global_cursor.x() + 10, global_cursor.y() + 18)

        # Gather the editor font for the preview editor.
        editor_font = self.editor.font()

        self._link_preview_popup.show_for_path(path, global_pos, editor_font)

    def _resolve_link_target(self, target: str, quick: bool = False) -> Path | None:
        """Resolve a link/wikilink target to an absolute Path, or None.
        If *quick* is True, skip the full rglob search (used for link
        highlighting — the click handler still does the full search)."""
        _LOG.debug("_resolve_link_target: %s", target)
        target_path = Path(target)
        if target_path.is_absolute():
            exists = target_path.exists()
            return target_path if exists else None

        base = self._file_path.parent if self._file_path else Path.cwd()
        vault_root = (
            self._attachments_dir.parent.resolve()
            if self._attachments_dir is not None
            else None
        )

        # 1. Same directory as the source file.
        candidates = [base / target_path]
        if target_path.suffix.lower() not in (".md", ".markdown"):
            candidates.append(base / (target + ".md"))
            candidates.append(base / (target + ".markdown"))
        for p in candidates:
            if p.is_file():
                return p.resolve()

        # 2. Attachments directory (by filename).
        if self._attachments_dir is not None:
            candidate = self._attachments_dir / target_path.name
            if candidate.is_file():
                return candidate.resolve()

        # 3. Proximity search: walk up the directory tree (max 5 levels).
        if vault_root is not None:
            check_dir = base.resolve()
            for _ in range(5):
                if check_dir == vault_root or check_dir.parent == check_dir:
                    break
                check_dir = check_dir.parent
                pc = check_dir / target_path
                if pc.is_file():
                    return pc.resolve()
                if target_path.suffix.lower() not in (".md", ".markdown"):
                    for ext in (".md", ".markdown"):
                        p2 = check_dir / (target + ext)
                        if p2.is_file():
                            return p2.resolve()
                    for ext in self._IMG_EXTS | self._PDF_EXTS:
                        p2 = check_dir / (target + ext)
                        if p2.is_file():
                            return p2.resolve()

        # 4. Extension fallback in the base + attachments dir.
        if target_path.suffix.lower() not in self._IMG_EXTS | self._PDF_EXTS:
            for ext in self._IMG_EXTS | self._PDF_EXTS:
                p = base / (target + ext)
                if p.is_file():
                    return p.resolve()
                if self._attachments_dir is not None:
                    p2 = self._attachments_dir / (target_path.name + ext)
                    if p2.is_file():
                        return p2.resolve()

        # 5. Full recursive search of the vault root (skipped for quick checks).
        if quick:
            return None

        search_root = vault_root if vault_root is not None else base
        target_name = target_path.name.lower()
        try:
            for p in search_root.rglob("*"):
                if p.is_file() and p.name.lower() == target_name:
                    try:
                        if any(
                            part.startswith(".")
                            for part in p.relative_to(search_root).parts
                        ):
                            continue
                    except ValueError:
                        pass
                    return p.resolve()
        except PermissionError:
            pass

        return None

    def _refresh_link_highlights(self) -> None:
        """Mark unresolved links in red using extra selections.
        Skips large files (>2000 lines) for performance."""
        editor = self.editor
        text = editor.toPlainText()
        lines = text.count("\n") + 1
        if lines > 2000:
            self._broken_link_selections = []
            self._apply_all_selections()
            return

        fmt = QTextCharFormat()
        fmt.setUnderlineColor(QColor("#e06c75"))
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)

        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        broken: list[QTextEdit.ExtraSelection] = []

        for pattern, target_group in ((self._LINK_RE, 2), (self._WIKILINK_RE, 1)):
            for m in pattern.finditer(text):
                target = m.group(target_group)
                # Skip URLs, email links, etc.
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                # Skip if the link resolves correctly.
                if self._resolve_link_target(target, quick=True) is not None:
                    continue

                sel = QTextEdit.ExtraSelection()
                sel.cursor = editor.textCursor()
                sel.cursor.setPosition(m.start())
                sel.cursor.setPosition(m.end(), QTextCursor.MoveMode.KeepAnchor)
                sel.format = fmt
                broken.append(sel)

        self._broken_link_selections = broken
        self._apply_all_selections()

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
        """Intercept events for custom editor behavior.

        Handles:
          - Resize → update line-number margin width
          - KeyPress → smart Tab/Backtab indentation
          - MouseMove → link detection popup (400 ms hover timer)
          - MouseButtonRelease → Ctrl+click link navigation
          - DragEnter/Leave/Move → file drop from explorer
          - Drop → insert file path or image
          - Wheel + Ctrl → zoom in/out
        """
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
            if event.type() == QEvent.Type.KeyPress:
                _LOG.debug("eventFilter: KeyPress key=%d", event.key())
                key_event = event  # type: ignore[assignment]
                if key_event.key() == Qt.Key.Key_V and bool(
                    key_event.modifiers() & Qt.KeyboardModifier.ControlModifier
                ):
                    if self._paste_image_from_clipboard():
                        return True

        elif obj is self._viewport:
            if event.type() == QEvent.Type.MouseMove:
                self._on_mouse_move(event)  # type: ignore[arg-type]
            elif event.type() == QEvent.Type.MouseButtonPress:
                self._mouse_press_pos = event.position().toPoint()  # type: ignore[attr-defined]
            elif event.type() == QEvent.Type.MouseButtonRelease:
                return self._on_mouse_click(event)  # type: ignore[arg-type]
            elif event.type() == QEvent.Type.DragEnter:
                _LOG.debug("eventFilter: DragEnter")
                self._on_drag_enter(event)  # type: ignore[arg-type]
                if not self._drag_active:
                    return False
                return True
            elif event.type() == QEvent.Type.DragLeave:
                self._drag_active = False
                return False
            elif event.type() == QEvent.Type.DragMove:
                if self._drag_active:
                    event.acceptProposedAction()  # type: ignore[attr-defined]
                    return True
                return False
            elif event.type() == QEvent.Type.Drop:
                _LOG.debug("eventFilter: Drop urls=%s", [url.toString() for url in event.mimeData().urls()])
                if self._drag_active and self._on_drop(event):  # type: ignore[arg-type]
                    return True
                self._drag_active = False
            elif event.type() == QEvent.Type.Wheel:
                we = event  # type: ignore[assignment]
                if we.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    delta = 1 if we.angleDelta().y() > 0 else -1
                    _LOG.debug("eventFilter: Wheel zoom factor=%.2f", float(delta))
                    if we.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        self.zoom_preview(delta)
                    else:
                        self.zoom_editor(delta)
                    return True

        elif obj is self._preview_viewport and event.type() == QEvent.Type.Wheel:
            we = event  # type: ignore[assignment]
            if we.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = 1 if we.angleDelta().y() > 0 else -1
                self.zoom_preview(delta)
                return True

        elif obj is self._preview_stack and event.type() == QEvent.Type.Resize:
            self._preview_timer.start()

        return super().eventFilter(obj, event)

    def _paste_image_from_clipboard(self) -> bool:
        """Paste clipboard content: file URLs (any type) or bitmap image.
        Returns True if handled."""

        _LOG.debug("_paste_image_from_clipboard")

        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False

        # 1) Try file URLs first (copy from Explorer / file manager) — any file type
        mime = clipboard.mimeData()
        if mime is not None and mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_file() and self._handle_file_drop(path):
                        return True

        # 2) Try bitmap data (copy from browser / screenshot)
        img = clipboard.image()
        if not img.isNull():
            if self._attachments_dir is None:
                return False
            import datetime

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"paste_{ts}.png"
            dest = self._attachments_dir / filename
            self._attachments_dir.mkdir(parents=True, exist_ok=True)
            if not img.save(str(dest), "PNG"):
                return False
            return self._handle_file_drop(dest)

        return False

    def _handle_file_drop(self, path: Path) -> bool:
        """Copy *path* to the attachments dir and insert a link.
        If the file is already inside the opened folder, use it in-place.
        Images get ``!`` prefix; other files get plain links.
        Link style (md vs wikilink) respects the user setting."""
        # Determine the vault root (parent of attachments dir).
        vault_root = (
            self._attachments_dir.parent.resolve()
            if self._attachments_dir
            else None
        )

        # If the file is already inside the vault, link it in-place.
        if vault_root is not None:
            try:
                path.resolve().relative_to(vault_root)
                _LOG.debug("_handle_file_drop: in-vault file — linking in-place %s", path.name)
                return self._insert_file_link(path)
            except ValueError:
                pass

        # Otherwise copy to the attachments directory.
        _LOG.debug("_handle_file_drop: copying to attachments")
        dest_dir = self._attachments_dir
        if dest_dir is None:
            base = self._file_path.parent if self._file_path else Path.cwd()
            dest_dir = base / "attachments"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        if dest.exists():
            stem, ext = path.stem, path.suffix
            n = 1
            while dest.exists():
                dest = dest_dir / f"{stem}_{n}{ext}"
                n += 1
        import shutil
        try:
            if dest.resolve() != path.resolve():
                shutil.copy2(str(path), str(dest))
        except OSError:
            return False
        return self._insert_file_link(dest)

    def _insert_file_link(self, dest: Path) -> bool:
        """Insert a markdown or wikilink for *dest*, using relative paths
        when possible. Images get ``!`` prefix."""
        link = None

        # If the file is inside the attachments directory, use just the filename
        # — the resolver already knows to look there.
        if self._attachments_dir is not None:
            try:
                dest.resolve().relative_to(self._attachments_dir.resolve())
                link = dest.name
            except ValueError:
                pass

        # Otherwise compute a relative path from the current file.
        if link is None and self._file_path and self._file_path.parent:
            try:
                rel = dest.resolve().relative_to(
                    self._file_path.parent.resolve(), walk_up=True
                )
                link = rel.as_posix()
            except ValueError:
                pass

        # Fallback: absolute path.
        if link is None:
            link = dest.as_posix()

        is_image = dest.suffix.lower() in self._IMG_EXTS
        if self._link_style == "wiki":
            syntax = f"![[{link}]]" if is_image else f"[[{link}]]"
        else:
            syntax = f"![{dest.stem}]({link})" if is_image else f"[{dest.stem}]({link})"

        _LOG.debug("_insert_file_link: %s style=%s link=%s", dest.name, self._link_style, link)
        cursor = self.editor.textCursor()
        cursor.insertText(syntax)
        self.editor.setFocus()
        return True

    def _on_drag_enter(self, event) -> None:
        """Accept drag events that contain any local file."""
        self._drag_active = False
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    self._drag_active = True
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _on_drop(self, event) -> bool:
        """Handle dropped files — copy to attachments dir and insert a link.
        Returns True if any file was handled."""
        if not event.mimeData().hasUrls():
            return False

        handled = False
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_file() and self._handle_file_drop(path):
                    handled = True

        if handled:
            event.acceptProposedAction()
        else:
            event.ignore()
        return handled

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.title_changed.emit()
