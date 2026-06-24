"""Hover popup that previews the target of a Markdown/wikilink."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap, QTextOption
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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

    _MAX_W = 520
    _MAX_H = 380

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
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

        # --- Text editor (markdown / plain text) ---
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
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

        ext = path.suffix.lower()

        if ext in self._IMG_EXTS:
            self._show_image(path)
        elif ext in self._PDF_EXTS:
            self._show_pdf(path)
        else:
            self._show_text(path, editor_font)

        self._header.setText(str(path))
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

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = f"[Cannot read file: {path.name}]"

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
            self._image_label.setText(f"[Cannot display: {path.name}]")
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
            self._image_label.setText(f"[Cannot render: {path.name}]")
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

        screen: QScreen | None = app.screenAt(pos)
        if screen is None:
            screen = app.primaryScreen()
        if screen is None:
            self.move(pos)
            return

        geo = screen.availableGeometry()
        sz = self.size()
        x = pos.x()
        y = pos.y()

        if x + sz.width() > geo.right():
            x = geo.right() - sz.width()
        if y + sz.height() > geo.bottom():
            y = max(geo.top(), pos.y() - sz.height() - 4)
        if x < geo.left():
            x = geo.left()

        self.move(x, y)

    # ------------------------------------------------------------------
    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.cancel_hide()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.hide_popup()
