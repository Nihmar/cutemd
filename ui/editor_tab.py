"""Single editor+preview tab for the tabbed interface."""

import re
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token
from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPixmap,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QWheelEvent,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from markdown.tools import BLOCK_OPEN_TYPES, add_heading_ids
from ui.markdown_completer import DEFAULT_SMART_EDITING, MarkdownAutoCompleter
from ui.syntax_highlighter import MarkdownHighlighter


class PreviewTextBrowser(QTextBrowser):
    """QTextBrowser that loads local images via loadResource() override."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_dir: Path | None = None
        self._image_cache: dict[tuple[int, str], QImage] = {}

    def set_base_dir(self, d: Path) -> None:
        resolved = d.resolve()
        if self._base_dir != resolved:
            self._image_cache.clear()
            self._base_dir = resolved

    @property
    def _max_width(self) -> int:
        return max(self.width(), 200)

    def loadResource(self, resource_type: int, url: QUrl):
        url_str = url.toString()
        cache_key = (resource_type, url_str)
        full = self._image_cache.get(cache_key)
        if full is not None:
            return EditorTab._fit_image(full, self._max_width)

        if resource_type == int(QTextDocument.ImageResource) and self._base_dir is not None:
            resolved = self._resolve_image_path(url_str)
            if resolved is not None:
                try:
                    img = QImage(str(resolved))
                except Exception:
                    img = QImage()
                if not img.isNull():
                    self._image_cache[cache_key] = img
                    return EditorTab._fit_image(img, self._max_width)

        return super().loadResource(resource_type, url)

    def _resolve_image_path(self, src: str) -> Path | None:
        p = Path(src)
        if "://" in src or src.startswith("data:") or src.startswith("file:"):
            return None
        if p.is_absolute():
            return p if p.is_file() else None
        resolved = (self._base_dir / p).resolve()
        if resolved.is_file():
            return resolved
        return EditorTab._search_image(p.name, self._base_dir)



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
        painter.fillRect(event.rect(), QColor(self._editor.palette().color(self._editor.palette().ColorRole.Window)))

        block = self._editor.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(self._editor.blockBoundingGeometry(block).translated(self._editor.contentOffset()).top())
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
                        0, top, self.width() - 4, self._editor.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number,
                    )
                elif self._mode == 2:
                    painter.drawText(
                        0, top, self.width() - 4, self._editor.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "·",
                    )
            block = block.next()
            top = bottom
            bottom = top + int(self._editor.blockBoundingRect(block).height()) if block.isValid() else top
            block_num += 1

    @staticmethod
    def _should_draw_line(line: int, total: int) -> bool:
        return line == 1 or line == total or line % 5 == 0


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
    file_link_clicked = Signal(str)

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
        self._current_line_sel: object = None
        self._is_binary_preview = False
        self._pan_active = False

        # Hover state for clickable links
        self._hover_link_key: tuple[int, int, int] | None = None  # (block, start, end)

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

        # --- Line numbers ---
        self._line_number_area = LineNumberArea(self.editor)
        self._update_line_number_area_width()
        self.editor.blockCountChanged.connect(
            self._update_line_number_area_width
        )
        self.editor.updateRequest.connect(self._update_line_number_area)
        self.editor.cursorPositionChanged.connect(self._on_highlight_current_line)
        self.editor.installEventFilter(self)
        self._viewport = self.editor.viewport()
        self._viewport.setMouseTracking(True)
        self._viewport.installEventFilter(self)
        self._completer = MarkdownAutoCompleter(self.editor, smart_editing, self)

        # --- Preview stack (page 0 = text browser, page 1 = image, page 2 = PDF) ---
        self.preview = PreviewTextBrowser()
        self.preview.setReadOnly(True)
        self.preview.setOpenExternalLinks(True)

        self._image_view = QLabel()
        self._image_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_scroll = QScrollArea()
        self._image_scroll.setWidgetResizable(True)
        self._image_scroll.setWidget(self._image_view)
        self._image_scroll.viewport().installEventFilter(self)

        self._pdf_view = QWidget()
        pdf_lay = QVBoxLayout(self._pdf_view)
        pdf_lay.setContentsMargins(0, 0, 0, 0)

        # Navigation bar
        nav = QHBoxLayout()
        self._pdf_prev_btn = QPushButton("\u25c0")  # ◀
        self._pdf_prev_btn.setFixedWidth(32)
        self._pdf_page_label = QLabel("0 / 0")
        self._pdf_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pdf_next_btn = QPushButton("\u25b6")  # ▶
        self._pdf_next_btn.setFixedWidth(32)
        self._pdf_open_btn = QPushButton(self.tr("Open externally"))
        nav.addStretch()
        nav.addWidget(self._pdf_prev_btn)
        nav.addWidget(self._pdf_page_label)
        nav.addWidget(self._pdf_next_btn)
        nav.addSpacing(10)
        nav.addWidget(self._pdf_open_btn)
        nav.addStretch()
        nav_widget = QWidget()
        nav_widget.setLayout(nav)

        self._pdf_page_view = QLabel()
        self._pdf_page_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pdf_scroll = QScrollArea()
        self._pdf_scroll.setWidgetResizable(True)
        self._pdf_scroll.setWidget(self._pdf_page_view)
        self._pdf_scroll.viewport().installEventFilter(self)

        pdf_lay.addWidget(nav_widget)
        pdf_lay.addWidget(self._pdf_scroll)
        self._pdf_prev_btn.clicked.connect(self._pdf_prev_page)
        self._pdf_next_btn.clicked.connect(self._pdf_next_page)
        self._pdf_open_btn.clicked.connect(self._on_open_pdf_externally)

        self._preview_stack = QStackedWidget()
        self._preview_stack.addWidget(self.preview)       # index 0
        self._preview_stack.addWidget(self._image_scroll) # index 1
        self._preview_stack.addWidget(self._pdf_view)     # index 2
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
        if self._is_binary_preview:
            return False
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
        self._preview_stack.setVisible(visible)
        if visible:
            self._update_preview()

    def set_editor_font(self, family: str, size: int) -> None:
        """Change the editor font family and size."""
        self._editor_font_family = family
        self._editor_font_size = size
        self._apply_editor_font()

    def set_line_number_mode(self, mode: int) -> None:
        """Set line number display mode (0=off, 1=all, 2=every 5th)."""
        self._line_number_area.set_mode(mode)
        self._update_line_number_area_width()

    def set_smart_editing(self, settings: dict[str, Any]) -> None:
        self._completer.update_settings(settings)

    def set_preview_font(self, family: str, size: int) -> None:
        """Change the preview font family and size and re-render."""
        self._preview_font_family = family
        self._preview_font_size = size
        self._update_preview()

    _MD_EXTS = frozenset({".md", ".markdown"})
    _IMG_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"})
    _PDF_EXTS = frozenset({".pdf"})

    _PARA_IMG_RE = re.compile(r'<p>\s*(<img\s[^>]+>)\s*</p>')
    _WIKILINK_IMG_RE = re.compile(r'!\[\[([^\]]+?)(?:\|([^\]]*?))?\]\]')

    @staticmethod
    def _preprocess_wikilink_images(text: str) -> str:
        """Convert ![[wikilink]] image syntax to standard Markdown ![](...)."""
        def _repl(m: re.Match) -> str:
            target = m.group(1).strip()
            alt = m.group(2).strip() if m.group(2) else target
            return f"![{alt}]({target})"
        return EditorTab._WIKILINK_IMG_RE.sub(_repl, text)

    @staticmethod
    def _search_image(filename: str, start_dir: Path) -> Path | None:
        """Search for *filename* in *start_dir* and all subdirectories
        up to 5 levels deep, then try up to 4 parent directories
        (each searched 5 levels deep as well)."""
        target = filename.lower()
        seen: set[Path] = set()

        dirs_to_search: list[Path] = [start_dir.resolve()]
        # Walk up to 4 parent levels to gather search roots
        d = start_dir.resolve()
        for _ in range(4):
            p = d.parent
            if p == d:
                break
            dirs_to_search.append(p)
            d = p

        for root in dirs_to_search:
            stack = [(root, 0)]
            while stack:
                d, depth = stack.pop()
                if d in seen:
                    continue
                seen.add(d)
                try:
                    for entry in d.iterdir():
                        if entry.is_file() and entry.name.lower() == target:
                            return entry.resolve()
                        if entry.is_dir() and depth < 5:
                            stack.append((entry, depth + 1))
                except PermissionError:
                    continue
        return None

    @staticmethod
    def _fit_image(img: QImage, max_width: int) -> QImage:
        """Scale *img* to fit within *max_width*, preserving aspect ratio."""
        if img.width() <= max_width:
            return img
        return img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)

    def load_file(self, path: Path) -> None:
        """Load *path* into the editor, replacing current content."""
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
        self._is_binary_preview = False
        self.editor.setReadOnly(False)
        self._preview_stack.setCurrentIndex(0)
        self._splitter.setSizes([500, 500])
        self.title_changed.emit()

        # Enable syntax highlighting only for Markdown files
        if ext in self._MD_EXTS:
            self._highlighter.setDocument(self.editor.document())
        else:
            self._highlighter.setDocument(None)  # type: ignore[arg-type]

    def _load_image(self, path: Path) -> None:
        """Display an image in a dedicated QLabel."""
        self.editor.setPlainText(
            self.tr("Image preview — {}").format(path.name)
        )
        self.editor.setReadOnly(True)
        self._highlighter.setDocument(None)  # type: ignore[arg-type]
        self._saved_text = ""

        self._original_pixmap = QPixmap(str(path))
        self._image_zoom = 1.0
        if not self._original_pixmap.isNull():
            self._rescale_image()
        else:
            self._image_view.setText(self.tr("Cannot display this image format."))
        self._preview_stack.setCurrentIndex(1)
        self._is_binary_preview = True
        self._splitter.setSizes([0, 1000])

    def _rescale_image(self) -> None:
        """Rescale the stored pixmap to fit the current viewport size * zoom."""
        if not hasattr(self, "_original_pixmap") or self._original_pixmap.isNull():
            return
        zoom = getattr(self, "_image_zoom", 1.0)
        size = self._image_scroll.viewport().size()
        scaled = self._original_pixmap.scaled(
            size * zoom, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self._image_view.setPixmap(scaled)
        self._image_view.setToolTip(f"Zoom: {int(zoom * 100)}%")

    def _load_pdf(self, path: Path) -> None:
        """Display PDF pages via QPdfDocument."""
        self.editor.setPlainText(
            self.tr("PDF — {}").format(path.name)
        )
        self.editor.setReadOnly(True)
        self._highlighter.setDocument(None)  # type: ignore[arg-type]
        self._saved_text = ""
        self._pdf_path = path.resolve()

        self._pdf_doc = QPdfDocument()
        self._pdf_doc.load(str(self._pdf_path))
        self._pdf_page = 0
        self._pdf_zoom = 1.0
        self._pdf_page_count = max(self._pdf_doc.pageCount(), 0)
        self._render_pdf_page()
        self._preview_stack.setCurrentIndex(2)
        self._is_binary_preview = True
        self._splitter.setSizes([0, 1000])

    def _render_pdf_page(self) -> None:
        if self._pdf_page_count == 0:
            self._pdf_page_view.setText(self.tr("Cannot render this PDF."))
            self._pdf_page_label.setText("0 / 0")
            return
        zoom = getattr(self, "_pdf_zoom", 1.0)
        size = self._pdf_scroll.viewport().size() * zoom
        img = self._pdf_doc.render(self._pdf_page, QSize(int(size.width()), int(size.height())))
        self._pdf_page_view.setPixmap(QPixmap.fromImage(img))
        self._pdf_page_label.setText(f"{self._pdf_page + 1} / {self._pdf_page_count}")
        self._pdf_prev_btn.setEnabled(self._pdf_page > 0)
        self._pdf_next_btn.setEnabled(self._pdf_page < self._pdf_page_count - 1)

    def _pdf_prev_page(self) -> None:
        if self._pdf_page > 0:
            self._pdf_page -= 1
            self._render_pdf_page()

    def _pdf_next_page(self) -> None:
        if self._pdf_page < self._pdf_page_count - 1:
            self._pdf_page += 1
            self._render_pdf_page()

    def _on_open_pdf_externally(self) -> None:
        from PySide6.QtGui import QDesktopServices

        if hasattr(self, "_pdf_path"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._pdf_path)))

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
    # Line number helpers
    # ------------------------------------------------------------------
    def _update_line_number_area_width(self, _count: int = 0) -> None:
        w = self._line_number_area._line_number_area_width() if self._line_number_area._mode != 0 else 0
        self.editor.setViewportMargins(w, 0, 0, 0)
        cr = self.editor.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), w, cr.height())
        )

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.editor.viewport().rect()):
            self._update_line_number_area_width()

    def _on_highlight_current_line(self) -> None:
        if not self.isVisible():
            return
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(
            self.editor.palette().color(self.editor.palette().ColorRole.AlternateBase)
        )
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.editor.textCursor()
        sel.cursor.clearSelection()
        self._current_line_sel = sel
        self._apply_all_selections()

    def _apply_all_selections(self) -> None:
        parts: list = []
        if self._current_line_sel is not None:
            parts.append(self._current_line_sel)
        parts.extend(getattr(self, "_find_selections", []))
        self.editor.setExtraSelections(parts)

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
        if hasattr(self, "_line_number_area"):
            self._update_line_number_area_width()

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
        if not self._preview_visible or self._is_binary_preview:
            return
        raw_text = self.editor.toPlainText()
        text = self._preprocess_wikilink_images(raw_text)
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

        base_dir = self._file_path.parent if self._file_path else Path.cwd()
        self.preview.set_base_dir(base_dir)
        body_html = EditorTab._PARA_IMG_RE.sub(
            r'<p style="margin-top:0px;margin-bottom:0px">\1</p>', body_html
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
        if self._syncing_scroll > 0 or not self._preview_visible or self._is_binary_preview:
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
        if self._syncing_scroll > 0 or not self._preview_visible or self._is_binary_preview:
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
            extra_sel = QTextEdit.ExtraSelection()
            extra_sel.format = fmt
            extra_sel.cursor = sel
            self._find_selections.append(extra_sel)
            cursor = doc.find(term, cursor, flags)
        self._apply_all_selections()

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
        self._apply_all_selections()

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
        self._find_selections = []

    def close_find(self) -> None:
        """Hide the find bar and clear highlights."""
        self._find_bar.setVisible(False)
        self._clear_highlights()
        self.editor.setFocus()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------
    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is self.editor:
            if event.type() == QEvent.Type.Resize:
                cr = self.editor.contentsRect()
                self._line_number_area.setGeometry(
                    QRect(cr.left(), cr.top(), self._line_number_area.sizeHint().width(), cr.height())
                )
                return super().eventFilter(obj, event)

        elif obj is self._viewport:
            if event.type() == QEvent.Type.MouseMove:
                self._on_mouse_move(event)  # type: ignore[arg-type]
            elif event.type() == QEvent.Type.MouseButtonRelease:
                return self._on_mouse_click(event)  # type: ignore[arg-type]

        elif obj in (self._image_scroll.viewport(), self._pdf_scroll.viewport()):
            return self._on_media_viewport_event(obj, event)

        elif obj is self._preview_stack and event.type() == QEvent.Type.Resize:
            self._preview_timer.start()

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Shared zoom + pan for image / PDF viewports
    # ------------------------------------------------------------------

    def _on_media_viewport_event(self, obj: object, event: QEvent) -> bool:
        vp = obj
        if event.type() == QEvent.Type.Resize:
            self._media_refresh(obj)
            return False

        if event.type() == QEvent.Type.Wheel:
            we: QWheelEvent = event  # type: ignore[assignment]
            if we.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = we.angleDelta().y() / 120.0
                zoom_attr = "_image_zoom" if obj is self._image_scroll.viewport() else "_pdf_zoom"
                cur = getattr(self, zoom_attr, 1.0)
                setattr(self, zoom_attr, max(0.1, min(10.0, cur + delta * 0.15)))
                self._media_refresh(obj)
                return True

        if event.type() == QEvent.Type.MouseButtonPress:
            me: QMouseEvent = event  # type: ignore[assignment]
            if me.button() == Qt.MouseButton.MiddleButton:
                self._pan_active = True
                self._pan_last = me.position().toPoint()
                vp.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True

        if event.type() == QEvent.Type.MouseMove:
            if getattr(self, "_pan_active", False):
                me: QMouseEvent = event  # type: ignore[assignment]
                pt = me.position().toPoint()
                delta = self._pan_last - pt
                self._pan_last = pt
                h = vp.horizontalScrollBar()
                v = vp.verticalScrollBar()
                if h:
                    h.setValue(h.value() + delta.x())
                if v:
                    v.setValue(v.value() + delta.y())
                return True

        if event.type() == QEvent.Type.MouseButtonRelease:
            me: QMouseEvent = event  # type: ignore[assignment]
            if me.button() == Qt.MouseButton.MiddleButton:
                self._pan_active = False
                vp.setCursor(Qt.CursorShape.ArrowCursor)
                return True

        return False

    def _media_refresh(self, obj: object) -> None:
        if obj is self._image_scroll.viewport():
            self._rescale_image()
        elif obj is self._pdf_scroll.viewport():
            self._render_pdf_page()

    # ------------------------------------------------------------------
    # Clickable link navigation (hover underline + click to open)
    # ------------------------------------------------------------------

    _LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    _WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

    @classmethod
    def _link_range_at(cls, pos_in_block: int, text: str) -> tuple[str, int, int] | None:
        """Return (target, start, end) if *pos_in_block* falls inside a
        markdown link or wikilink, else None."""
        for m in cls._WIKILINK_RE.finditer(text):
            if m.start() <= pos_in_block <= m.end():
                return (m.group(1).split("|")[0].strip(), m.start(), m.end())
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

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.title_changed.emit()
        super().changeEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(800, 600)
