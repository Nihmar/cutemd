"""QTextBrowser subclass that loads local images via loadResource() override."""

import base64
from pathlib import Path

from core.logging import setup_logging

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QApplication, QTextBrowser

from markdown.image_utils import (
    needs_loading,
    resolve_image_path,
)

_LOG = setup_logging("cutemd.preview_browser")


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


class PreviewTextBrowser(QTextBrowser):
    """QTextBrowser that loads local images via loadResource() override."""

    file_link_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self._base_dir: Path | None = None
        self._attachments_dir: Path | None = None
        self.anchorClicked.connect(self._on_anchor_clicked)

    def set_base_dir(self, d: Path) -> None:
        resolved = d.resolve()
        if self._base_dir != resolved:
            self._base_dir = resolved

    def set_attachments_dir(self, d: Path | None) -> None:
        resolved = d.resolve() if d is not None else None
        self._attachments_dir = resolved

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Forward clicked links (e.g. wrapped images) to the tab.

        External URLs are opened via the system browser.
        ``http://cutemd-copy/`` URLs copy the encoded code to the clipboard.
        """
        url_str = url.toString()
        _LOG.debug("_on_anchor_clicked: %s", url_str[:120])

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
            return
        if url_str.startswith(("http://", "https://", "www.")):
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(url)
            return
        target = url.toLocalFile() if url.isLocalFile() else url_str
        if target:
            self.file_link_clicked.emit(target)

    @property
    def _max_width(self) -> int:
        return max(self.width(), 200)

    def loadResource(self, resource_type: int, url: QUrl):
        # Images now have absolute file:// URLs embedded by add_img_dimensions.
        # This is a safety net for any relative URLs that slip through.
        if resource_type == int(QTextDocument.ImageResource):
            url_str = url.toLocalFile() if url.isLocalFile() else url.toString()
            if self._base_dir is not None and needs_loading(url_str):
                resolved = resolve_image_path(url_str, self._base_dir, self._attachments_dir)
                if resolved is not None:
                    try:
                        img = QImage(str(resolved))
                    except Exception:
                        img = QImage()
                    if not img.isNull():
                        return img
        return super().loadResource(resource_type, url)
