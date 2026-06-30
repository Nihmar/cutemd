"""Theme manager — applies and propagates theme changes."""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication, QWidget

from ui.qss_loader import load_qss
from ui.themes import Theme, get_theme, system_theme


class ThemeManager(QObject):
    """Central theme controller. Emits theme_applied when the theme changes."""

    theme_applied = Signal(Theme)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current: Theme | None = None
        self._theme_id: str = "system"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def current(self) -> Theme:
        """Return the currently active Theme (resolved). Raises if never set."""
        if self._current is None:
            self._current = system_theme()
            self._theme_id = "system"
        return self._current

    @property
    def theme_id(self) -> str:
        return self._theme_id

    def resolve(self, theme_id: str) -> Theme:
        """Resolve a theme ID to a Theme object (without applying it)."""
        if theme_id == "system":
            return system_theme()
        return get_theme(theme_id)

    def apply(self, theme_id: str) -> None:
        """Apply *theme_id* globally: palette, QSS, pygments style."""
        from md_parser.tools import set_pygments_style

        self._theme_id = theme_id
        self._current = self.resolve(theme_id)

        set_pygments_style(self._current.pygments_style)

        pal = self._current.build_palette()
        app = QApplication.instance()
        if app is not None:
            app.setPalette(pal)
            app.setStyleSheet(load_qss(pal))

        self.theme_applied.emit(self._current)

    def apply_to_widget(self, widget: QWidget) -> None:
        """Apply current palette + stylesheet to a single widget."""
        if self._current is None:
            return
        widget.setPalette(self._current.build_palette())

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    @property
    def icon_color(self):
        return self.current.icon_color

    @property
    def is_dark(self) -> bool:
        return self.current.is_dark
