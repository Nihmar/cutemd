"""Single editor+preview tab for the tabbed interface."""

import re
import time
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
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.animation_speed import animation_duration_ms
from core.constants import (
    BROKEN_LINK_LINE_LIMIT,
    DOC_EXTS,
    IMG_EXTS,
    LARGE_FILE_THRESHOLD,
    MD_EXTS,
    PDF_EXTS,
)
from core.file_utils import read_file_with_encoding
from core.link_resolution import build_line_anchor_map, resolve_link_target
from core.logging import setup_logging
from core.spell_checker import SpellChecker
from markdown.html_builder import (
    preprocess_tags,
    preprocess_wikilink_images,
    preprocess_wikilinks,
    strip_frontmatter,
)
from ui.async_doc_renderer import AsyncDocRenderer
from ui.drop_handler import DropHandler
from ui.find_bar import FindBar
from ui.image_viewer import ImageViewer
from ui.line_number_area import LineNumberArea
from ui.link_manager import LinkManager
from ui.link_preview_popup import LinkPreviewPopup
from ui.markdown_completer import MarkdownAutoCompleter
from ui.pdf_viewer import PdfViewer
from ui.preview_browser import PreviewWebEngineView, get_image_size
from ui.preview_worker import PreviewWorker
from ui.syntax_highlighter import MarkdownHighlighter

_LOG = setup_logging("cutemd.editor_tab")


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
    file_link_clicked = Signal(str, str)  # target, display_text
    encoding_changed = Signal(str)
    preview_detached = Signal(bool)  # True when preview is detached

    _MD_EXTS = MD_EXTS
    _IMG_EXTS = IMG_EXTS
    _PDF_EXTS = PDF_EXTS
    _DOC_EXTS = DOC_EXTS

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
        self._frontmatter_offset: int = 0  # lines stripped by frontmatter removal
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
        self._mouse_press_pos: QPoint | None = None
        self._detached_window: QWidget | None = None
        self._splitter_sizes: list[int] = []
        self._preview_viewport: object = None  # set after preview widget creation
        self._toc_in_preview: bool = False

        # --- Drop handler (drag&drop + clipboard paste) ---
        self._drop_handler = DropHandler(self)

        # Async preview state.
        self._preview_busy = False
        self._preview_pending = False

        # Cached plain text — invalidated only when document changes.
        self._cached_text: str = ""
        self._cached_text_hash: int = 0
        self._cached_words: str = "0 words"

        # --- Link preview popup ---
        self._link_preview_popup = LinkPreviewPopup(self)

        self._editor_font_family = editor_font_family
        self._editor_font_size = editor_font_size
        self._preview_font_family = preview_font_family
        self._preview_font_size = preview_font_size

        # --- Editor ---
        self.editor = QPlainTextEdit()
        self.editor.setAcceptDrops(True)

        # --- Link manager (detection, hover, broken-link highlights) ---
        self._link_mgr = LinkManager(self)

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
        self.editor.textChanged.connect(self._invalidate_text_cache)
        self.editor.textChanged.connect(self._update_word_count)
        self.editor.cursorPositionChanged.connect(self._emit_status)

        self._spell_checker = SpellChecker()
        self._highlighter = MarkdownHighlighter(
            self.editor.document(), spell_checker=self._spell_checker
        )
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
        self._completer.img_tag_inserted.connect(self._on_img_tag_inserted)
        self._link_style = (smart_editing or {}).get("link_style", "md")

        # --- Preview stack ---
        self.preview = PreviewWebEngineView()
        self.preview.setReadOnly(True)
        self.preview.setOpenLinks(False)
        self.preview.setOpenExternalLinks(False)
        self.preview.file_link_clicked.connect(
            lambda target: self.file_link_clicked.emit(target, "")
        )
        self.preview.checkbox_toggled.connect(self._on_checkbox_toggled)
        if self._attachments_dir is not None:
            self.preview.set_attachments_dir(self._attachments_dir)
        self._preview_viewport = self.preview  # QWebEngineView is its own viewport
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
        # Editor → Preview
        self.editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)
        # Preview → Editor: 30fps polling — JS stores position in _cutemd_line,
        # Python reads it. Much lighter than URL navigation per frame.
        self._preview_poll_timer = QTimer(self)
        self._preview_poll_timer.setInterval(33)  # ~30fps
        self._preview_poll_timer.timeout.connect(self._poll_preview_line)

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
        layout.addWidget(self._find_bar, 0)

        # Slot for external toolbar (inserted by MainWindow)
        self._toolbar_slot = layout

        layout.addWidget(splitter, 1)  # stretch 1 = take all remaining space

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

    def set_theme(
        self,
        theme: str,
        pygments_style: str = "",
        theme_bg: str = "",
        theme_fg: str = "",
        theme_mid: str = "",
    ) -> None:
        _LOG.debug(
            "DIAG set_theme: theme=%s old=%s pygments=%s old_pygments=%s bg=%s",
            theme,
            self._theme,
            pygments_style,
            getattr(self, "_pygments_style", ""),
            theme_bg,
        )
        theme_changed = theme != self._theme
        pygments_changed = pygments_style and pygments_style != getattr(
            self, "_pygments_style", ""
        )
        colors_changed = theme_bg and theme_bg != getattr(self, "_theme_bg", "")
        if theme_changed or pygments_changed or colors_changed:
            self._theme = theme
            if pygments_style:
                self._pygments_style = pygments_style
            if theme_bg:
                self._theme_bg = theme_bg
                self.preview.set_page_background(theme_bg)
            if theme_fg:
                self._theme_fg = theme_fg
            if theme_mid:
                self._theme_mid = theme_mid
            self._last_rendered_hash = 0
            self._highlighter.set_theme(theme)
            self._link_mgr.popup.set_theme(theme)
            _LOG.debug(
                "DIAG set_theme: calling _update_preview, cached_text_len=%d",
                len(self._cached_text),
            )
            self._update_preview()

    def set_preview_visible(self, visible: bool) -> None:
        _LOG.debug("set_preview_visible: %s", visible)
        if visible == self._preview_visible:
            return
        self._preview_visible = visible
        if not visible:
            self._preview_poll_timer.stop()

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
        new_size = max(
            self._ZOOM_MIN, min(self._ZOOM_MAX, self._editor_font_size + delta)
        )
        if new_size == self._editor_font_size:
            return
        self._editor_font_size = new_size
        self._apply_editor_font()

    def zoom_preview(self, delta: int) -> None:
        """Zoom the preview font by *delta* points (+1/-1)."""
        new_size = max(
            self._ZOOM_MIN, min(self._ZOOM_MAX, self._preview_font_size + delta)
        )
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
        _LOG.debug(
            "load_file: ext=%s _DOC_EXTS=%s hit=%s",
            ext,
            self._DOC_EXTS,
            ext in self._DOC_EXTS,
        )
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

        text, encoding = read_file_with_encoding(path)
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
        self._large_file = path.stat().st_size > LARGE_FILE_THRESHOLD
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
        name_map = {
            ".docx": self.tr("Word"),
            ".xlsx": self.tr("Excel"),
            ".pptx": self.tr("PowerPoint"),
            ".cbz": self.tr("CBZ"),
            ".epub": self.tr("EPUB"),
            ".csv": self.tr("CSV"),
            ".tsv": self.tr("TSV"),
        }
        label = name_map.get(ext, self.tr("Document"))
        _LOG.debug("_load_document: %s (%s) label=%s", path.name, ext, label)

        self.editor.setPlainText(self.tr("{} \u2014 {}").format(label, path.name))
        self.editor.setReadOnly(True)
        self._highlighter.setDocument(None)
        self._saved_text = ""
        self._is_binary_preview = True
        self._splitter.setSizes([0, 1000])
        self.title_changed.emit()

        # Show a loading indicator while rendering in background.
        self.preview.setPlainText(self.tr("Rendering\u2026"))
        self._preview_stack.setCurrentIndex(0)

        self._doc_thread = AsyncDocRenderer(path, self)
        self._doc_thread.result.connect(self._on_doc_rendered)
        self._doc_thread.start()

    def _on_doc_rendered(self, html: str) -> None:
        _LOG.debug("DIAG _on_doc_rendered: len=%d", len(html))
        self._preview_stack.setCurrentIndex(0)
        QTimer.singleShot(0, lambda: self._deferred_set_html(html))
        self._refresh_link_highlights()

    def _on_checkbox_toggled(self, payload: str) -> None:
        """Handle checkbox toggle from preview: payload is "LINE|STATE"."""
        _LOG.debug("_on_checkbox_toggled: %s payload=%s", payload, self._cached_text[:50] if self._cached_text else '')
        if self._is_binary_preview:
            return
        try:
            line_part, state = payload.split("|", 1)
            line = int(line_part)
        except (ValueError, TypeError):
            return
        doc = self.editor.document()
        if line >= doc.blockCount():
            _LOG.debug("_on_checkbox_toggled: line %d >= blockCount %d", line, doc.blockCount())
            return
        block = doc.findBlockByNumber(line)
        text = block.text()
        _LOG.debug("_on_checkbox_toggled: block text=%s", text)
        new_text = text.replace("- [ ]", "- [x]", 1) if state == "checked" else text.replace("- [x]", "- [ ]", 1)
        if new_text == text:
            _LOG.debug("_on_checkbox_toggled: no change needed")
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new_text)
        self._dirty = self.is_modified
        self.modified_changed.emit(self._dirty)
        # Don't re-render — the browser already toggled the checkbox in the DOM.
        # Cancel any pending debounce so a stale render doesn't undo it.
        self._preview_timer.stop()

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
                path, _ = QFileDialog.getSaveFileName(
                    self,
                    self.tr("Save Markdown file"),
                    "",
                    self.tr("Markdown files (*.md *.markdown);;All files (*)"),
                )
                if not path:
                    return False
                self._write_file(Path(path))
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
        extra.extend(self._link_mgr._broken_link_selections)
        self.editor.setExtraSelections(extra)

    def _invalidate_text_cache(self) -> None:
        """Rebuild the cached plain text after document content changes."""
        self._cached_text = self.editor.toPlainText()
        self._cached_text_hash = hash(self._cached_text)
        self._link_mgr.invalidate_cache()
        self._cum_heights = None  # invalidate cumulative height cache

    def _emit_status(self) -> None:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.status_changed.emit(f"{line}:{col}", self._cached_words)

    def _update_word_count(self) -> None:
        """Recompute word count from cached text (only on textChanged)."""
        if self._large_file:
            self._cached_words = self.tr("{} words (large file)").format(
                len(self._cached_text.split())
            )
        else:
            self._cached_words = self.tr("{} words").format(
                len(self._cached_text.split())
            )

    def _on_text_changed(self) -> None:
        _LOG.debug("TEXT_CHANGED editor_line=%d",
                   self.editor.firstVisibleBlock().blockNumber())
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

    def _on_img_tag_inserted(self) -> None:
        """Open a file picker for the img src after tag insertion."""
        cursor = self.editor.textCursor()
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        src_start = block_text.rfind('src="', 0, pos)
        if src_start < 0:
            return
        quote_start = src_start + 5
        from PySide6.QtWidgets import QFileDialog

        start_dir = str(self._attachments_dir) if self._attachments_dir else str(
            self._file_path.parent if self._file_path else Path.cwd())

        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select image"), start_dir,
            self.tr("Images (*.png *.jpg *.jpeg *.gif *.bmp *.svg *.webp);;All files (*)"),
        )
        if path:
            dest = Path(path)
            base = self._file_path.parent if self._file_path else Path.cwd()
            try:
                rel = dest.resolve().relative_to(base.resolve())
                dest_str = rel.as_posix()
            except (ValueError, OSError):
                dest_str = dest.as_posix()

            block_start = cursor.block().position()
            c = QTextCursor(self.editor.document())
            c.setPosition(block_start + quote_start)
            c.movePosition(QTextCursor.MoveOperation.Right,
                          QTextCursor.MoveMode.KeepAnchor, 0)
            c.insertText(dest_str)
            self.editor.setTextCursor(c)
            self.editor.setFocus()

    def set_toc_in_preview(self, enabled: bool) -> None:
        if self._toc_in_preview != enabled:
            self._toc_in_preview = enabled
            self._last_rendered_hash = 0
            self._update_preview()

    def set_spell_check_langs(self, langs: list[str]) -> None:
        _LOG.debug("set_spell_check_langs: %s", langs)
        self._spell_checker.set_langs(langs)
        self._highlighter.rehighlight()

    def load_custom_dict(self, folder_path: Path) -> None:
        """Load the per-folder custom dictionary into the spell checker."""
        self._spell_checker.load_custom_dict(folder_path)

    def add_custom_word(self, word: str) -> None:
        """Add a word to the custom dictionary and re-highlight."""
        self._spell_checker.add_word(word)
        self._highlighter.rehighlight()

    # ------------------------------------------------------------------
    # Table editing
    # ------------------------------------------------------------------

    def edit_table(self) -> None:
        """Open the table popup editor for the table at cursor."""
        from ui.table_editor import TablePopupEditor, parse_table, rows_to_markdown

        cursor = self.editor.textCursor()
        parsed = parse_table(cursor)
        if parsed is None:
            return
        rows, sep_idx, _cur_col = parsed

        dlg = TablePopupEditor(rows, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_rows = dlg.result_rows()

        # Replace the table in the document
        from ui.table_editor import _find_table_range
        rng = _find_table_range(cursor)
        if rng is None:
            return
        top, bottom = rng
        doc = self.editor.document()
        start_block = doc.findBlockByNumber(top)
        end_block = doc.findBlockByNumber(bottom)
        edit_cursor = QTextCursor(start_block)
        edit_cursor.setPosition(
            end_block.position() + end_block.length() - 1,
            QTextCursor.MoveMode.KeepAnchor,
        )
        edit_cursor.insertText(rows_to_markdown(new_rows).rstrip("\n"))

    def add_table_row(self) -> None:
        """Append a new row to the table at cursor."""
        from ui.table_editor import _find_table_range, _ROW_RE

        cursor = self.editor.textCursor()
        rng = _find_table_range(cursor)
        if rng is None:
            return
        _top, bottom = rng
        doc = self.editor.document()
        last_block = doc.findBlockByNumber(bottom)
        line = last_block.text()
        m = _ROW_RE.match(line)
        if not m:
            return
        ncols = len(m.group(1).split("|"))
        cells = " | ".join(" " for _ in range(ncols))
        new_cursor = QTextCursor(last_block)
        new_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        new_cursor.insertText("\n| " + cells + " |")

    def add_table_column(self) -> None:
        """Append a new column to the right of the table at cursor."""
        from ui.table_editor import _find_table_range, _ROW_RE, _SEP_RE

        cursor = self.editor.textCursor()
        rng = _find_table_range(cursor)
        if rng is None:
            return
        top, bottom = rng
        doc = self.editor.document()
        for n in range(top, bottom + 1):
            block = doc.findBlockByNumber(n)
            text = block.text()
            if _SEP_RE.match(text):
                new_text = text.rstrip() + " ---|"
            elif _ROW_RE.match(text):
                new_text = text.rstrip() + "  |"
            else:
                continue
            tc = QTextCursor(block)
            tc.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            tc.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
            tc.insertText(new_text)

    def insert_table_dialog(self) -> None:
        """Open the new-table dimensions dialog and insert a table skeleton."""
        from ui.table_editor import InsertTableDialog, rows_to_markdown

        dlg = InsertTableDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        nrows, ncols = dlg.dimensions()
        rows = [["" for _ in range(ncols)] for _ in range(nrows)]
        md = rows_to_markdown(rows).rstrip("\n")
        cursor = self.editor.textCursor()
        start = cursor.position()
        cursor.insertText("\n" + md + "\n")
        # Place cursor in the first data cell (skip header + separator if nrows > 1).
        cursor.setPosition(start + 3)
        if nrows > 1:
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.MoveAnchor, 2)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, 2)
        self.editor.setTextCursor(cursor)

    def insert_toolbar(self, toolbar: QWidget) -> None:
        """Insert *toolbar* above find bar (index 0)."""
        self._toolbar_slot.insertWidget(0, toolbar)

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
        _LOG.debug(
            "DIAG _update_preview: visible=%s binary=%s large=%s text_len=%d",
            self._preview_visible,
            self._is_binary_preview,
            self._large_file,
            len(self._cached_text),
        )
        if not self._preview_visible or self._is_binary_preview or self._large_file:
            return
        raw_text = self._cached_text
        if not raw_text.strip():
            return  # nothing to preview
        text = strip_frontmatter(raw_text)
        text = preprocess_tags(preprocess_wikilinks(preprocess_wikilink_images(text)))
        # Debug: count inline tags
        _tag_count = text.count('<span style="color:#d19a66')
        if _tag_count:
            _LOG.debug("_update_preview: %d inline #tag(s) wrapped", _tag_count)
        self._frontmatter_offset = len(raw_text.split("\n")) - len(text.split("\n"))
        text_hash = hash(text)
        _LOG.debug("_update_preview: hash=%s", text_hash)
        # Anchor map is computed in the worker thread.
        # Use stale map until the new one arrives.

        if self._line_anchor_map:
            first_block = self.editor.firstVisibleBlock()
            current_line = max(0, first_block.blockNumber() - self._frontmatter_offset)
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
                getattr(self, "_pygments_style", ""),
                getattr(self, "_theme_bg", ""),
                getattr(self, "_theme_fg", ""),
                getattr(self, "_theme_mid", ""),
            )
        )
        if params_hash == self._last_rendered_hash:
            return
        self._pending_render_hash = params_hash

        # Collect render params.
        # Note: "md" is NOT passed — the worker creates its own parser
        # because MarkdownIt doesn't survive cross-thread signal marshaling.
        params: dict[str, Any] = {
            "text": text,
            "preview_css": self._preview_css,
            "theme": self._theme,
            "font_family": self._preview_font_family,
            "font_size": self._preview_font_size,
            "base_dir": base_dir,
            "max_width": max(pw, 200),
            "get_image_size": get_image_size,
            "attachments_dir": self._attachments_dir,
            "theme_bg": getattr(self, "_theme_bg", ""),
            "theme_fg": getattr(self, "_theme_fg", ""),
            "theme_mid": getattr(self, "_theme_mid", ""),
            "frontmatter_offset": self._frontmatter_offset,
            "toc_enabled": self._toc_in_preview,
        }

        if self._preview_busy:
            _LOG.debug("_update_preview: debounce skipped (busy)")
            self._preview_pending = True
            self._pending_preview_params = params
            return

        self._preview_busy = True
        _LOG.debug(
            "_update_preview: emitting render_requested, text_bytes=%d params_hash=%s",
            len(text),
            params_hash,
        )
        # Delay spinner — fast renders don't need it.
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setSingleShot(True)
        self._spinner_timer.timeout.connect(
            lambda: self._preview_stack.setCurrentIndex(3)
        )
        self._spinner_timer.start(100)
        _LOG.debug("_update_preview: rendering %d bytes", len(text))
        self._preview_worker.render_requested.emit(params)
        self._link_mgr.schedule_broken_refresh()

    def _on_preview_ready(self, html: str) -> None:
        _LOG.debug(
            "PREVIEW_READY len=%d editor_line=%d",
            len(html) if html else 0,
            self.editor.firstVisibleBlock().blockNumber(),
        )
        self._preview_busy = False
        # Cancel spinner if it hasn't fired yet.
        if hasattr(self, "_spinner_timer"):
            self._spinner_timer.stop()

        self._syncing_scroll += 1
        self._preview_stack.setCurrentIndex(0)  # back to preview
        # Defer setHtml by one event loop iteration so that the QStackedWidget
        # has time to actually show the QWebEngineView before Chromium loads.
        # Without this, the widget is still hidden and loadFinished returns False.
        QTimer.singleShot(0, lambda: self._deferred_set_html(html))
        self._syncing_scroll -= 1

    def _deferred_set_html(self, html: str) -> None:
        _LOG.debug("SET_HTML len=%d editor_line=%d",
                   len(html),
                   self.editor.firstVisibleBlock().blockNumber())
        # Disconnect any stale loadFinished handler from a previous load.
        try:
            self.preview.loadFinished.disconnect()
        except RuntimeError:
            pass

        def on_load(ok: bool) -> None:
            self.preview.loadFinished.disconnect(on_load)
            _LOG.debug("LOAD_DONE ok=%s editor_line=%d",
                       ok, self.editor.firstVisibleBlock().blockNumber())
            self.preview._inject_scroll_listener()
            self._inject_anchor_map()  # ← aggiunto qui
            self._pending_sync_anchor = self._last_anchor
            self._sync_preview_scroll()
            if self._preview_visible:
                self._preview_poll_timer.start()

        self.preview.loadFinished.connect(on_load)
        self.preview.setHtml(html)

        # Compute anchor map from the rendered text (on main thread).
        # Use the *preprocessed* text that was sent to the worker.
        if self._cached_text:
            rendered_text = strip_frontmatter(self._cached_text)
            rendered_text = preprocess_tags(
                preprocess_wikilinks(preprocess_wikilink_images(rendered_text))
            )
            try:
                self._line_anchor_map = build_line_anchor_map(self._md, rendered_text)
            except Exception:
                pass

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

    def _sync_preview_scroll(self) -> None:
        if self._syncing_scroll > 0:
            return
        anchor = self._pending_sync_anchor
        if not anchor:
            return
        _LOG.debug("PREVIEW_SCROLL anchor=%s", anchor)
        self._syncing_scroll += 1
        js = (
            f"(function(){{"
            f"var el=document.querySelector('a[name=\"{anchor}\"]');"
            f"if(el){{window._cutemd_suppress=Date.now()+300;el.scrollIntoView({{block:'start',behavior:'instant'}});}}"
            f"}})();"
        )
        self.preview.page().runJavaScript(js)
        self._poll_blocked_until = time.monotonic() + 0.5
        self._syncing_scroll -= 1
        self._pending_sync_anchor = ""

    def _on_editor_scrolled(self, _value: int = 0) -> None:
        # Hide link preview when scrolling.
        self._link_mgr.popup.hide()
        self._link_mgr._hovered_link_target = None
        self._link_mgr._link_preview_show_timer.stop()

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
        current_line = max(0, first_block.blockNumber() - self._frontmatter_offset)
        if current_line >= len(line_map):
            return
        anchor_idx = line_map[current_line]
        anchor = f"b{anchor_idx}"

        # Block poll while the user is actively scrolling — even within
        # the same section.  Without this the poll fires before the user
        # lifts the scrollbar and snaps the editor to a stale heading line.
        self._poll_blocked_until = time.monotonic() + 0.5

        if anchor == self._last_anchor:
            return
        _LOG.debug("EDITOR_SCROLL line=%d anchor=%s", current_line, anchor)
        self._last_anchor = anchor
        self._pending_scroll_anchor = anchor

        if not hasattr(self, "_editor_scroll_timer"):
            self._editor_scroll_timer = QTimer(self)
            self._editor_scroll_timer.setSingleShot(True)
            self._editor_scroll_timer.setInterval(50)
            self._editor_scroll_timer.timeout.connect(self._do_editor_scroll_preview)

        self._editor_scroll_timer.start()

    def _do_editor_scroll_preview(self) -> None:
        anchor = getattr(self, "_pending_scroll_anchor", "")
        if not anchor or self._syncing_scroll > 0:
            return
        self._syncing_scroll += 1
        js = (
            f"(function(){{"
            f"var el=document.querySelector('a[name=\"{anchor}\"]');"
            f"if(el){{window._cutemd_suppress=Date.now()+300;el.scrollIntoView({{block:'start',behavior:'instant'}});}}"
            f"}})();"
        )
        self.preview.page().runJavaScript(js)
        self._syncing_scroll -= 1

    def _poll_preview_line(self) -> None:
        """Poll window._cutemd_line at 30fps and scroll the editor to match."""
        if self._syncing_scroll > 0:
            return
        blocked = getattr(self, '_poll_blocked_until', 0.0)
        if time.monotonic() < blocked:
            return
        js = "JSON.stringify({l:window._cutemd_line||'',b:!!window._cutemd_at_bottom})"
        self.preview.page().runJavaScript(js, self._on_poll_result)

    def _on_poll_result(self, line_str: str) -> None:
        if self._syncing_scroll > 0:
            return
        if not line_str:
            _LOG.debug("POLL empty result (page not loaded?)")
            return
        try:
            import json
            data = json.loads(line_str)
            target_line = int(data.get("l", "0") or "0")
            at_bottom = data.get("b", False)
        except (ValueError, json.JSONDecodeError):
            return
        _last = getattr(self, "_last_poll_line", None)
        if _last is not None and target_line == _last and not at_bottom:
            return

        # Guard: if the preview reports a line that is much earlier than
        # the last known position, wait one extra tick before acting.
        # This prevents false syncs caused by browser reflows (e.g. KaTeX
        # rendering temporarily zeroes the page height, Chromium clamps
        # scrollY to 0, the scroll listener sets _cutemd_line = 0, and
        # the poll would otherwise snap the editor to line 0).
        if (
            _last is not None
            and target_line < _last - 50
            and not at_bottom
            and _last > 0
        ):
            if not getattr(self, "_poll_confirm_pending", False):
                self._poll_confirm_pending = True
                _LOG.debug("POLL jump guard: target=%d last=%d diff=%d — waiting 1 tick",
                          target_line, _last, _last - target_line)
                return
            _LOG.debug("POLL jump guard: confirmed after 1 tick, target=%d", target_line)
        self._poll_confirm_pending = False

        self._last_poll_line = target_line

        # Accumulate block heights to get pixel-precise Y position.
        # Use cached cumulative heights (rebuilt on textChanged).
        cum_heights = getattr(self, '_cum_heights', None)
        if cum_heights is None or target_line >= len(cum_heights):
            # Rebuild cache (shouldn't normally happen)
            doc = self.editor.document()
            count = doc.blockCount()
            cum = [0.0]
            for i in range(count):
                block = doc.findBlockByNumber(i)
                rect = self.editor.blockBoundingRect(block)
                cum.append(cum[-1] + rect.height())
            cum_heights = cum
            self._cum_heights = cum

        px_y = cum_heights[target_line]
        total_h = cum_heights[-1]

        self._syncing_scroll += 1
        sb = self.editor.verticalScrollBar()
        if sb.maximum() > 0 and total_h > 0:
            if at_bottom:
                sb.setValue(sb.maximum())
            else:
                sb_px_range = max(total_h - self.editor.viewport().height(), 1)
                ratio = min(px_y, sb_px_range) / sb_px_range
                sb.setValue(int(ratio * sb.maximum()))
        self._syncing_scroll -= 1
        _LOG.debug("SYNC line=%-4d px=%d/%d first=%d",
                   target_line, px_y, total_h,
                   self.editor.firstVisibleBlock().blockNumber())

        self._pending_sync_anchor = ""

    # ------------------------------------------------------------------
    # Link detection & preview (delegated to LinkManager)
    # ------------------------------------------------------------------

    @classmethod
    def _link_range_at(
        cls, pos_in_block: int, text: str
    ) -> tuple[str, str, int, int] | None:
        return LinkManager.link_range_at(pos_in_block, text)

    def _on_mouse_move(self, event) -> None:
        pt = event.position().toPoint()
        cursor = self.editor.cursorForPosition(pt)
        block = cursor.block()
        self._link_mgr.on_mouse_move(
            cursor.positionInBlock(), block.text(), block.blockNumber()
        )

    def _on_mouse_click(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._mouse_press_pos is not None:
            release_pt = event.position().toPoint()
            if (release_pt - self._mouse_press_pos).manhattanLength() > 5:
                self._mouse_press_pos = None
                return False
        self._mouse_press_pos = None
        pt = event.position().toPoint()
        cursor = self.editor.cursorForPosition(pt)
        link = self._link_mgr.on_mouse_click(
            cursor.positionInBlock(), cursor.block().text()
        )
        if link:
            self.file_link_clicked.emit(link[0], link[1])
            return True
        return False

    def _on_link_preview_show(self) -> None:
        pass  # handled by LinkManager

    def _check_popup_cursor(self) -> None:
        pass  # handled by LinkManager

    def _resolve_link_target(self, target: str, quick: bool = False) -> Path | None:
        return self._link_mgr._resolve_link_target(target, quick)

    def _refresh_link_highlights(self) -> None:
        self._link_mgr.refresh_broken_links(self._cached_text)

    # ------------------------------------------------------------------
    def _clear_highlights(self) -> None:
        self._apply_all_selections()

    def open_find(self) -> None:
        self._find_bar.open()

    def close_find(self) -> None:
        self._find_bar.close()

    def find_bar_visible(self) -> bool:
        return self._find_bar.isVisible()

    def detach_preview(self) -> bool:
        """Move the preview pane into a standalone window.
        Returns True if detached, False if re-attached.
        """
        if self._detached_window is not None:
            self._attach_preview()
            return False

        idx = self._splitter.indexOf(self._preview_stack)
        if idx < 0:
            return False
        self._splitter_sizes = self._splitter.sizes()
        self._preview_stack.setParent(None)

        self._detached_window = QWidget(None, Qt.WindowType.Window)
        self._detached_window.setWindowTitle(
            self.tr("Preview \u2014 {}").format(self.display_name())
        )
        self._detached_window.resize(600, 700)
        wl = QVBoxLayout(self._detached_window)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(self._preview_stack)
        self._detached_window.installEventFilter(self)
        self._detached_window.show()
        self.preview_detached.emit(True)
        _LOG.debug("detach_preview: detached")
        return True

    def _attach_preview(self) -> None:
        """Move the preview back into the splitter."""
        if self._detached_window is None:
            return
        self._detached_window.removeEventFilter(self)
        self._preview_stack.setParent(None)
        self._detached_window.hide()
        self._detached_window.deleteLater()
        self._detached_window = None
        self._splitter.insertWidget(1, self._preview_stack)
        if hasattr(self, "_splitter_sizes") and self._splitter_sizes:
            self._splitter.setSizes(self._splitter_sizes)
        self.preview_detached.emit(False)
        _LOG.debug("_attach_preview: re-attached")

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
          - Close → re-attach detached preview window
        """
        if obj is self._detached_window and event.type() == QEvent.Type.Close:
            self._attach_preview()
            return True

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
                # Tab navigation inside tables
                if key_event.key() == Qt.Key.Key_Tab:
                    from ui.table_editor import move_to_next_cell
                    if not key_event.modifiers():
                        if move_to_next_cell(self.editor):
                            return True
                elif key_event.key() == Qt.Key.Key_Backtab:
                    from ui.table_editor import move_to_prev_cell
                    if move_to_prev_cell(self.editor):
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
                if not self._drop_handler.drag_active:
                    return False
                return True
            elif event.type() == QEvent.Type.DragLeave:
                self._drop_handler._drag_active = False
                return False
            elif event.type() == QEvent.Type.DragMove:
                if self._drop_handler.drag_active:
                    event.acceptProposedAction()  # type: ignore[attr-defined]
                    return True
                return False
            elif event.type() == QEvent.Type.Drop:
                _LOG.debug(
                    "eventFilter: Drop urls=%s",
                    [url.toString() for url in event.mimeData().urls()],
                )
                if self._drop_handler.drag_active and self._on_drop(event):  # type: ignore[arg-type]
                    return True
                self._drop_handler._drag_active = False
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

        elif (
            self._preview_viewport is not None
            and obj is self._preview_viewport
            and event.type() == QEvent.Type.Wheel
        ):
            we = event  # type: ignore[assignment]
            if we.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = 1 if we.angleDelta().y() > 0 else -1
                self.zoom_preview(delta)
                return True

        elif obj is self._preview_stack and event.type() == QEvent.Type.Resize:
            self._preview_timer.start()

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Drag & drop / clipboard paste (delegated to DropHandler)
    # ------------------------------------------------------------------

    def _paste_image_from_clipboard(self) -> bool:
        return self._drop_handler.paste_from_clipboard()

    def _handle_file_drop(self, path) -> bool:
        return self._drop_handler._handle_file_drop(path)

    def _insert_file_link(self, dest) -> bool:
        return self._drop_handler._insert_file_link(dest)

    def _on_drag_enter(self, event) -> None:
        self._drop_handler.on_drag_enter(event)

    def _on_drop(self, event) -> bool:
        return self._drop_handler.on_drop(event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.title_changed.emit()

    # ------------------------------------------------------------------
    # Scroll listener
    # ------------------------------------------------------------------

    def _inject_anchor_map(self) -> None:
        """Inject window._cutemd_anchor_map = {anchor_idx: src_line} for preview→editor sync."""
        if not self._line_anchor_map:
            return
        rev: dict[int, int] = {}
        for src_line, anc_idx in enumerate(self._line_anchor_map):
            if anc_idx not in rev:  # prima riga per ogni anchor
                rev[anc_idx] = src_line
        import json

        self.preview.page().runJavaScript(
            f"window._cutemd_anchor_map={json.dumps(rev)};"
        )
