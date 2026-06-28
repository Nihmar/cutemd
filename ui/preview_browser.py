"""QWebEngineView replacement for the preview pane.

Provides:
- PreviewWebEnginePage  — custom QWebEnginePage with link/wikilink interception
- PreviewWebEngineView  — QWebEngineView with the same public API as
  the old PreviewTextBrowser so that EditorTab needs minimal changes
- get_image_size()     — QImage-based size provider (unchanged, used by html_builder)
"""

from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QImage,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from core.logging import setup_logging

_LOG = setup_logging("cutemd.preview_browser")


# ---------------------------------------------------------------------------
# Image size provider (unchanged — used by markdown/html_builder.py)
# ---------------------------------------------------------------------------

def _fit_image(img: QImage, max_width: int) -> QImage:
    if img.width() <= max_width:
        return img
    return img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)


def get_image_size(path_str: str, max_width: int) -> tuple[int, int] | None:
    """QImage-based size provider for markdown.image_utils.add_img_dimensions."""
    try:
        img = QImage(path_str)
    except Exception:
        return None
    if img.isNull():
        return None
    img = _fit_image(img, max_width)
    return (img.width(), img.height())


# ---------------------------------------------------------------------------
# Custom QWebEnginePage — navigation interception
# ---------------------------------------------------------------------------

class PreviewWebEnginePage(QWebEnginePage):
    """Custom QWebEnginePage that intercepts link/wikilink navigation.

    - ``http://cutemd-copy/`` URLs → decode and copy to clipboard
    - External http/https → open in system browser
    - Local file:// or plain paths → emit ``file_link_clicked``
    - Everything else → blocked (return False)
    """
    file_link_clicked = Signal(str)

    def acceptNavigationRequest(
        self, url: QUrl, nav_type, is_main_frame: bool
    ) -> bool:
        url_str = url.toString()
        _LOG.debug("acceptNavigationRequest: %s (nav_type=%s)",
                   url_str[:120], nav_type)

        # Copy-code interception
        if url_str.startswith("http://cutemd-copy/"):
            payload = url_str.removeprefix("http://cutemd-copy/")
            _LOG.debug("cutemd-copy payload length: %d", len(payload))
            try:
                decoded = base64.urlsafe_b64decode(payload).decode("utf-8")
                _LOG.debug("decoded %d chars to clipboard", len(decoded))
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(decoded)
                    _LOG.debug("clipboard.setText succeeded")
                else:
                    _LOG.debug("clipboard is None")
            except Exception as exc:
                _LOG.debug("cutemd-copy error: %s", exc)
            return False

        # External URLs → system browser
        if url_str.startswith(("http://", "https://", "www.")):
            QDesktopServices.openUrl(url)
            return False

        # Local file/image paths
        target = url.toLocalFile() if url.isLocalFile() else url_str
        if target:
            self.file_link_clicked.emit(target)
        return False  # Block all navigation


# ---------------------------------------------------------------------------
# Custom QWebEngineView — drop-in replacement for PreviewTextBrowser
# ---------------------------------------------------------------------------

class PreviewWebEngineView(QWebEngineView):
    """QWebEngineView with the same public API as the old QTextBrowser preview.

    Signals:
        file_link_clicked(str) — a local file path was clicked.
    """
    file_link_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._page = PreviewWebEnginePage(self)
        self.setPage(self._page)
        self._page.file_link_clicked.connect(self.file_link_clicked)

        self._base_dir: Path | None = None
        self._attachments_dir: Path | None = None

        # Allow loading file:// images from local content
        settings = self.page().settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )

    # ------------------------------------------------------------------
    # Public API — compatible with the old PreviewTextBrowser
    # ------------------------------------------------------------------

    def set_base_dir(self, d: Path) -> None:
        resolved = d.resolve()
        if self._base_dir != resolved:
            self._base_dir = resolved

    def set_attachments_dir(self, d: Path | None) -> None:
        resolved = d.resolve() if d is not None else None
        self._attachments_dir = resolved

    def setReadOnly(self, _read_only: bool) -> None:
        """No-op — kept for API compatibility with QTextBrowser."""
        pass

    def setOpenLinks(self, _open: bool) -> None:
        """No-op — navigation is handled by acceptNavigationRequest."""
        pass

    def setOpenExternalLinks(self, _open: bool) -> None:
        """No-op — external links are handled by acceptNavigationRequest."""
        pass

    def viewport(self):
        """Return a widget suitable for installing event filters.

        QWebEngineView is itself the visible widget, unlike QAbstractScrollArea
        which has a separate viewport().
        """
        return self

    def setPlainText(self, text: str) -> None:
        """Display plain text (used for "Rendering…" placeholder)."""
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        html = f"<!DOCTYPE html><html><body style='padding:16px'>{escaped}</body></html>"
        self.page().setContent(html.encode("utf-8"), "text/html;charset=utf-8")

    def setHtml(self, html: str) -> None:
        """Load HTML content. Uses setContent() internally to avoid the
        2 MB truncation limit of QWebEngineView.setHtml().
        """
        base_url = QUrl.fromLocalFile(str(self._base_dir)) if self._base_dir else QUrl()
        self.page().setContent(
            html.encode("utf-8"), "text/html;charset=utf-8", base_url
        )

    # ------------------------------------------------------------------
    # Context menu — block Chromium defaults
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        """Suppress the Chromium default context menu.
        The preview is read-only, so there is nothing useful to offer.
        """
        event.ignore()
