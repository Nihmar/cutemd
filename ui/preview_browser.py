"""QTextBrowser subclass that loads local images via loadResource() override."""

import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QTextBrowser

_IMG_EXTS_RE = re.compile(r"\.(png|jpg|jpeg|gif|bmp|svg|webp|ico)$", re.I)

_IMG_DIMS_RE = re.compile(r'(<img\s+)(src="([^"]*)")')
_PARA_IMG_RE = re.compile(r"<p>\s*(<a\b[^>]*></a>)?\s*(<img\b[^>]+>)\s*</p>")


def _needs_loading(src: str) -> bool:
    if not src or "://" in src or src.startswith("data:") or src.startswith("file:"):
        return False
    return bool(_IMG_EXTS_RE.search(src))


def _fit_image(img: QImage, max_width: int) -> QImage:
    if img.width() <= max_width:
        return img
    return img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)


def _search_image(filename: str, start_dir: Path) -> Path | None:
    """Case-insensitive recursive search for *filename* starting from
    *start_dir* and walking up to 4 parent levels (each searched 5
    levels deep)."""
    target = filename.lower()
    seen: set[Path] = set()

    dirs_to_search: list[Path] = [start_dir.resolve()]
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


def resolve_image_path(src: str, base_dir: Path) -> Path | None:
    """Resolve a relative image *src* to an absolute Path."""
    p = Path(src)
    if not _needs_loading(src) or p.is_absolute():
        return p if p.is_file() else None
    resolved = (base_dir / p).resolve()
    if resolved.is_file():
        return resolved
    return _search_image(p.name, base_dir)


def add_img_dimensions(html: str, base_dir: Path, max_width: int) -> str:
    """Add width/height attributes to local <img> tags."""
    def _repl(m: re.Match) -> str:
        prefix = m.group(1)
        src_attr = m.group(2)
        src = m.group(3)
        if not _needs_loading(src) or Path(src).is_absolute():
            return m.group(0)
        resolved = resolve_image_path(src, base_dir)
        if resolved is None:
            return m.group(0)
        try:
            img = QImage(str(resolved))
        except Exception:
            return m.group(0)
        if img.isNull():
            return m.group(0)
        img = _fit_image(img, max_width)
        return f'{prefix}{src_attr} width="{img.width()}" height="{img.height()}"'
    return _IMG_DIMS_RE.sub(_repl, html)


def fix_image_paragraphs(html: str) -> str:
    """Set zero margin and line-height on <p> tags that contain images."""
    return _PARA_IMG_RE.sub(
        r'<p style="margin-top:0px;margin-bottom:0px;line-height:0px;">\1\2</p>',
        html,
    )


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
