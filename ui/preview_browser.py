"""QTextBrowser subclass that loads local images via loadResource() override."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QTextBrowser

from markdown.image_utils import (
    fix_image_paragraphs,
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
            return _fit_image(full, self._max_width)

        if resource_type == int(QTextDocument.ImageResource) and self._base_dir is not None:
            resolved = resolve_image_path(url_str, self._base_dir)
            if resolved is not None:
                try:
                    img = QImage(str(resolved))
                except Exception:
                    img = QImage()
                if not img.isNull():
                    self._image_cache[cache_key] = img
                    return _fit_image(img, self._max_width)

        return super().loadResource(resource_type, url)
