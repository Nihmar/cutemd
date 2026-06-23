"""QTextBrowser subclass that loads local images via loadResource() override."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_dir: Path | None = None
        self._images_dir: Path | None = None

    def set_base_dir(self, d: Path) -> None:
        resolved = d.resolve()
        if self._base_dir != resolved:
            self._base_dir = resolved

    def set_images_dir(self, d: Path | None) -> None:
        resolved = d.resolve() if d is not None else None
        self._images_dir = resolved

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
