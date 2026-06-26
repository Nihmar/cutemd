"""Theme definitions — Qt-aware wrappers around core theme data."""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from core.theme_data import ThemeData, get_theme_data, ALL_THEMES_DATA

# Global Pygments style — updated when theme changes
PYGMENTS_STYLE: str = "default"


@dataclass
class Theme:
    id: str
    name: str
    is_dark: bool
    pygments_style: str  # Pygments style name for code blocks
    icon_color: QColor  # toolbar SVG icon colour

    # Palette colour roles
    window: QColor
    window_text: QColor
    base: QColor
    alternate_base: QColor
    text: QColor
    button: QColor
    button_text: QColor
    highlight: QColor
    highlighted_text: QColor
    mid: QColor
    midlight: QColor
    dark: QColor
    link: QColor
    tooltip_base: QColor
    tooltip_text: QColor

    def build_palette(self) -> QPalette:
        p = QPalette()
        p.setColor(QPalette.ColorRole.Window, self.window)
        p.setColor(QPalette.ColorRole.WindowText, self.window_text)
        p.setColor(QPalette.ColorRole.Base, self.base)
        p.setColor(QPalette.ColorRole.AlternateBase, self.alternate_base)
        p.setColor(QPalette.ColorRole.Text, self.text)
        p.setColor(QPalette.ColorRole.Button, self.button)
        p.setColor(QPalette.ColorRole.ButtonText, self.button_text)
        p.setColor(QPalette.ColorRole.Highlight, self.highlight)
        p.setColor(QPalette.ColorRole.HighlightedText, self.highlighted_text)
        p.setColor(QPalette.ColorRole.Mid, self.mid)
        p.setColor(QPalette.ColorRole.Midlight, self.midlight)
        p.setColor(QPalette.ColorRole.Dark, self.dark)
        p.setColor(QPalette.ColorRole.Link, self.link)
        p.setColor(QPalette.ColorRole.ToolTipBase, self.tooltip_base)
        p.setColor(QPalette.ColorRole.ToolTipText, self.tooltip_text)
        p.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        return p


def _theme_from_data(d: ThemeData) -> Theme:
    return Theme(
        id=d.id,
        name=d.name,
        is_dark=d.is_dark,
        pygments_style=d.pygments_style,
        icon_color=QColor(d.icon_color),
        window=QColor(d.window),
        window_text=QColor(d.window_text),
        base=QColor(d.base),
        alternate_base=QColor(d.alternate_base),
        text=QColor(d.text),
        button=QColor(d.button),
        button_text=QColor(d.button_text),
        highlight=QColor(d.highlight),
        highlighted_text=QColor(d.highlighted_text),
        mid=QColor(d.mid),
        midlight=QColor(d.midlight),
        dark=QColor(d.dark),
        link=QColor(d.link),
        tooltip_base=QColor(d.tooltip_base),
        tooltip_text=QColor(d.tooltip_text),
    )


ALL_THEMES: list[Theme] = [_theme_from_data(d) for d in ALL_THEMES_DATA]
_BY_ID: dict[str, Theme] = {t.id: t for t in ALL_THEMES}


def get_theme(theme_id: str) -> Theme:
    return _BY_ID.get(theme_id, ALL_THEMES[0])


def system_theme() -> Theme:
    """Return System theme resolved to dark or light based on OS preference."""
    from PySide6.QtWidgets import QApplication  # late import

    app = QApplication.instance()
    if app and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:  # type: ignore[attr-defined]
        return Theme(
            id="system",
            name="System (dark)",
            is_dark=True,
            pygments_style="monokai",
            icon_color=QColor(208, 208, 208),
            window=QColor(30, 30, 30),
            window_text=QColor(208, 208, 208),
            base=QColor(25, 25, 25),
            alternate_base=QColor(35, 35, 35),
            text=QColor(208, 208, 208),
            button=QColor(45, 45, 45),
            button_text=QColor(208, 208, 208),
            highlight=QColor(42, 130, 218),
            highlighted_text=QColor(255, 255, 255),
            mid=QColor(80, 80, 80),
            midlight=QColor(50, 50, 50),
            dark=QColor(120, 120, 120),
            link=QColor(42, 130, 218),
            tooltip_base=QColor(45, 45, 45),
            tooltip_text=QColor(235, 235, 235),
        )
    return _theme_from_data(get_theme_data("system"))
