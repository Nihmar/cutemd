"""Icon provider — renders SVG icons tinted with a color.  Cached."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from core.paths import resolve_path

_ICONS_DIR = resolve_path("ui", "icons")
_ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}


class IconProvider:
    """Colored SVG icon factory with cache."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, int], QIcon] = {}

    def make(self, name: str, color: QColor, size: int = 18) -> QIcon:
        cache_key = (name, color.name(), size)
        cached = self._cache.get(cache_key) or _ICON_CACHE.get(cache_key)
        if cached is not None:
            return cached

        from PySide6.QtSvg import QSvgRenderer

        path = str(_ICONS_DIR / f"{name}.svg")
        renderer = QSvgRenderer(path)

        svg = QPixmap(size, size)
        svg.fill(Qt.GlobalColor.transparent)
        painter = QPainter(svg)
        renderer.render(painter)
        painter.end()

        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.drawPixmap(0, 0, svg)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(result.rect(), color)
        painter.end()

        icon = QIcon(result)
        self._cache[cache_key] = icon
        _ICON_CACHE[cache_key] = icon
        return icon
