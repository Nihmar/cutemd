"""Hover popup that previews the target of a Markdown/wikilink."""

import csv
import zipfile
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap, QTextOption
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from markdown.document_renderers import epub_to_html, xlsx_to_html
from core.logging import setup_logging

_LOG = setup_logging("cutemd.link_preview_popup")
from ui.syntax_highlighter import MarkdownHighlighter


class LinkPreviewPopup(QFrame):
    """Popup window that shows a live preview of a linked file.

    Appears near the mouse cursor when hovering over a link in the editor.
    """

    _MD_EXTS = frozenset({".md", ".markdown"})
    _IMG_EXTS = frozenset(
        {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}
    )
    _PDF_EXTS = frozenset({".pdf"})
    _CSV_EXTS = frozenset({".csv", ".tsv"})
    _CBZ_EXTS = frozenset({".cbz"})
    _EPUB_EXTS = frozenset({".epub"})
    _XLSX_EXTS = frozenset({".xlsx"})

    _MAX_W = 520
    _MAX_H = 380

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)

        self._path: Path | None = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(250)
        self._hide_timer.timeout.connect(self._maybe_hide)
        self._mouse_over = False

        # CBZ gallery state
        self._cbz_images: list[tuple[bytes, str]] = []
        self._cbz_index: int = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Header bar with file path ---
        self._header = QLabel()
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header.setWordWrap(False)
        self._header.setFixedHeight(22)
        self._header.setStyleSheet(
            "background: #3c3c3c; color: #cccccc; font-size: 10px; padding: 2px 6px;"
        )
        layout.addWidget(self._header)

        # --- Text / HTML preview ---
        self._editor = QTextBrowser()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._editor.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self._editor.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._highlighter: MarkdownHighlighter | None = None
        layout.addWidget(self._editor)

        # --- Image viewer ---
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._image_label.setStyleSheet("background: palette(base);")
        self._image_label.hide()
        layout.addWidget(self._image_label)

        self.setMaximumSize(self._MAX_W, self._MAX_H)
        self.resize(self._MAX_W, self._MAX_H)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_theme(self, theme: str) -> None:
        """Update the syntax highlighter theme."""
        if self._highlighter is not None:
            self._highlighter.set_theme(theme)

    def show_for_path(
        self, path: Path, screen_pos, editor_font: QFont | None = None
    ) -> None:
        """Load *path* and show the popup at *screen_pos*."""
        if path == self._path and self.isVisible():
            self._move_within_screen(screen_pos)
            return

        self._path = path
        self._hide_timer.stop()
        self._mouse_over = True

        # Force-hide if visible so the WM accepts the new position
        # (Wayland/GNOME ignores move() on visible windows).
        was_visible = self.isVisible()
        if was_visible:
            self.hide()

        self._cbz_images = []

        self._header.setText(str(path))

        ext = path.suffix.lower()

        if ext in self._IMG_EXTS:
            self._show_image(path)
        elif ext in self._CBZ_EXTS:
            self._show_cbz(path)
        elif ext in self._PDF_EXTS:
            self._show_pdf(path)
        elif ext in self._CSV_EXTS:
            self._show_csv(path)
        elif ext in self._XLSX_EXTS:
            self._show_xlsx(path)
        elif ext in self._EPUB_EXTS:
            self._show_epub(path)
        else:
            self._show_text(path, editor_font)
        self._move_within_screen(screen_pos)
        self.setVisible(True)
        self.raise_()

    def hide_popup(self) -> None:
        """Schedule hide after a short delay (to avoid flicker)."""
        self._mouse_over = False
        self._hide_timer.start()

    def cancel_hide(self) -> None:
        """Cancel pending hide (e.g., mouse entered the popup)."""
        self._hide_timer.stop()
        self._mouse_over = True

    # ------------------------------------------------------------------
    # Internal preview methods
    # ------------------------------------------------------------------

    def _show_text(self, path: Path, editor_font: QFont | None) -> None:
        self._image_label.hide()
        self._editor.show()
        self._editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._editor.setWordWrapMode(QTextOption.WrapMode.NoWrap)

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = self.tr("[Cannot read file: {}]").format(path.name)

        self._editor.setPlainText(text)

        if editor_font is not None:
            self._editor.setFont(editor_font)

        ext = path.suffix.lower()
        if ext in self._MD_EXTS:
            if self._highlighter is None:
                self._highlighter = MarkdownHighlighter(self._editor.document())
            else:
                self._highlighter.setDocument(self._editor.document())
        elif self._highlighter is not None:
            self._highlighter.setDocument(None)

        self._editor.verticalScrollBar().setValue(0)

    def _show_image(self, path: Path) -> None:
        self._editor.hide()
        if self._highlighter is not None:
            self._highlighter.setDocument(None)

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._image_label.setText(self.tr("[Cannot display: {}]").format(path.name))
        else:
            scaled = pixmap.scaled(
                self._MAX_W - 10,
                self._MAX_H - 30,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)

        self._image_label.show()

    def _show_pdf(self, path: Path) -> None:
        self._editor.hide()
        if self._highlighter is not None:
            self._highlighter.setDocument(None)

        doc = QPdfDocument()
        doc.load(str(path))
        if doc.pageCount() == 0:
            self._image_label.setText(self.tr("[Cannot render: {}]").format(path.name))
            self._image_label.show()
            return

        page_size = doc.pagePointSize(0)
        aspect = (
            page_size.height() / page_size.width() if page_size.width() > 0 else 1.4
        )
        w = min(self._MAX_W - 10, int(page_size.width()))
        h = min(self._MAX_H - 30, int(w * aspect))
        if h > self._MAX_H - 30:
            h = self._MAX_H - 30
            w = int(h / aspect) if aspect > 0 else 1

        img = doc.render(0, QSize(w, h))
        self._image_label.setPixmap(QPixmap.fromImage(img))
        self._image_label.show()

    def _show_csv(self, path: Path) -> None:
        self._image_label.hide()
        self._editor.show()
        self._editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._editor.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        if self._highlighter is not None:
            self._highlighter.setDocument(None)

        try:
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            with open(path, encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                rows = list(reader)[:100]
        except Exception:
            self._editor.setPlainText(self.tr("[Cannot read: {}]").format(path.name))
            return

        if not rows:
            self._editor.setPlainText("")
            return

        col_widths = [0] * max(len(r) for r in rows)
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(cell))

        lines = [" \u2502 ".join(c.ljust(col_widths[i]) for i, c in enumerate(row)) for row in rows]
        self._editor.setPlainText("\n".join(lines))
        mono = QFont("Consolas", 9) if QFont("Consolas").exactMatch() else QFont("monospace", 9)
        self._editor.setFont(mono)

    def _show_cbz(self, path: Path) -> None:
        self._editor.hide()
        if self._highlighter is not None:
            self._highlighter.setDocument(None)

        self._cbz_images = []
        self._cbz_index = 0

        self._cbz_images = []
        self._cbz_index = 0

        try:
            with zipfile.ZipFile(path) as zf:
                for name in sorted(zf.namelist()):
                    ext = Path(name).suffix.lower()
                    if ext in self._IMG_EXTS:
                        data = zf.read(name)
                        pm = QPixmap()
                        if pm.loadFromData(data) and not pm.isNull():
                            self._cbz_images.append((data, name))
        except (zipfile.BadZipFile, FileNotFoundError):
            self._image_label.setText(self.tr("[Cannot read: file is corrupted]"))
            self._image_label.show()
            self._editor.hide()
            return
        except Exception:
            pass

        if not self._cbz_images:
            self._image_label.setText(self.tr("[Cannot display: {}]").format(path.name))
            self._image_label.show()
            return

        self._show_cbz_page(0)

    def _show_cbz_page(self, index: int) -> None:
        """Show the *index*-th image from the CBZ archive."""
        data, name = self._cbz_images[index]
        pixmap = QPixmap()
        if not pixmap.loadFromData(data) or pixmap.isNull():
            self._image_label.setText(self.tr("[Cannot display page: {}]").format(Path(name).name))
            self._image_label.show()
            return

        total = len(self._cbz_images)
        self._header.setText(f"\u25c0  {self._path.name}  [{index + 1}/{total}]  \u25b6")
        self._image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        scaled = pixmap.scaled(
            self._MAX_W - 10,
            self._MAX_H - 30,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        self._image_label.show()

    def mousePressEvent(self, event) -> None:
        """Navigate CBZ pages with mouse clicks (left half=prev, right half=next)."""
        if self._cbz_images and event.button() == Qt.MouseButton.LeftButton:
            w = self._image_label.width()
            if w > 0 and event.position().x() > w / 2:
                self._cbz_index = (self._cbz_index + 1) % len(self._cbz_images)
            else:
                self._cbz_index = (self._cbz_index - 1) % len(self._cbz_images)
            self._show_cbz_page(self._cbz_index)
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:
        """Navigate CBZ pages with the mouse wheel."""
        if self._cbz_images:
            if event.angleDelta().y() < 0:
                self._cbz_index = (self._cbz_index + 1) % len(self._cbz_images)
                self._show_cbz_page(self._cbz_index)
            elif event.angleDelta().y() > 0:
                self._cbz_index = (self._cbz_index - 1) % len(self._cbz_images)
                self._show_cbz_page(self._cbz_index)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        """Navigate CBZ pages with Left/Right arrow keys."""
        if self._cbz_images:
            if event.key() == Qt.Key.Key_Right:
                self._cbz_index = (self._cbz_index + 1) % len(self._cbz_images)
                self._show_cbz_page(self._cbz_index)
            elif event.key() == Qt.Key.Key_Left:
                self._cbz_index = (self._cbz_index - 1) % len(self._cbz_images)
                self._show_cbz_page(self._cbz_index)
            return
        super().keyPressEvent(event)

    def _show_epub(self, path: Path) -> None:
        self._image_label.hide()
        self._editor.show()
        if self._highlighter is not None:
            self._highlighter.setDocument(None)

        self._editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        html = epub_to_html(path, "")
        self._editor.setHtml(html)
        self._editor.verticalScrollBar().setValue(0)

    def _show_xlsx(self, path: Path) -> None:
        self._image_label.hide()
        self._editor.show()
        self._editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        if self._highlighter is not None:
            self._highlighter.setDocument(None)

        try:
            html = xlsx_to_html(path, "")
        except ImportError:
            html = f"<p>{self.tr('[Package openpyxl required for .xlsx preview]')}</p>"
        except Exception:
            html = f"<p>{self.tr('[Cannot read: {}]').format(path.name)}</p>"

        self._editor.setHtml(html)
        self._editor.verticalScrollBar().setValue(0)

    # ------------------------------------------------------------------
    # Delayed hide
    # ------------------------------------------------------------------

    def _maybe_hide(self) -> None:
        if not self._mouse_over:
            self.hide()

    def _move_within_screen(self, pos) -> None:
        """Move to *pos*, nudging the popup back on-screen if needed."""
        from PySide6.QtGui import QScreen
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            self.move(pos)
            return

        sz = self.size()
        x = pos.x()
        y = pos.y()

        screen: QScreen | None = app.screenAt(QPoint(x, y))
        if screen is None:
            screen = app.primaryScreen()
        if screen is None:
            self.move(pos)
            return

        geo = screen.availableGeometry()

        if x + sz.width() > geo.right():
            x = geo.right() - sz.width()
        if x < geo.left():
            x = geo.left()
        if y + sz.height() > geo.bottom():
            y = geo.bottom() - sz.height()
        if y < geo.top():
            y = geo.top()

        _LOG.debug("_move_within_screen: pos=%s final=(%d,%d) sz=%s geo=%s",
                    pos, x, y, sz, (geo.x(), geo.y(), geo.width(), geo.height()))
        self.move(x, y)
        _LOG.debug("_move_within_screen: actual pos=%s actual global=%s",
                    self.pos(), self.mapToGlobal(QPoint(0, 0)))

    # ------------------------------------------------------------------
    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.cancel_hide()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.hide_popup()
