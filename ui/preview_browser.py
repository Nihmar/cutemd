"""QTextBrowser subclass that loads local images via loadResource() override."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QTextBrowser

from markdown.image_utils import (
    needs_loading,
    resolve_image_path,
)


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
        self._base_dir: Path | None = None
        self._images_dir: Path | None = None
        self.anchorClicked.connect(self._on_anchor_clicked)

    def set_base_dir(self, d: Path) -> None:
        resolved = d.resolve()
        if self._base_dir != resolved:
            self._base_dir = resolved

    def set_images_dir(self, d: Path | None) -> None:
        resolved = d.resolve() if d is not None else None
        self._images_dir = resolved

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Forward clicked links (e.g. wrapped images) to the tab.
        External URLs are opened via the system browser."""
        url_str = url.toString()
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
                resolved = resolve_image_path(url_str, self._base_dir, self._images_dir)
                if resolved is not None:
                    try:
                        img = QImage(str(resolved))
                    except Exception:
                        img = QImage()
                    if not img.isNull():
                        return img
        return super().loadResource(resource_type, url)
