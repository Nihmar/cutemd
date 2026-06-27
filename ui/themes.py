"""Theme definitions — colour palettes and the Theme dataclass."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


@dataclass
class Theme:
    """A complete colour scheme for the application."""

    id: str
    name: str
    is_dark: bool
    pygments_style: str
    icon_color: QColor

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


# ---------------------------------------------------------------------------
# Built-in themes
# ---------------------------------------------------------------------------

SYSTEM_LIGHT = Theme(
    id="system",
    name="System",
    is_dark=False,
    pygments_style="default",
    icon_color=QColor("#303030"),
    window=QColor("#f0f0f0"),
    window_text=QColor("#1e1e1e"),
    base=QColor("#ffffff"),
    alternate_base=QColor("#f5f5f5"),
    text=QColor("#1e1e1e"),
    button=QColor("#f0f0f0"),
    button_text=QColor("#1e1e1e"),
    highlight=QColor("#2a82da"),
    highlighted_text=QColor("#ffffff"),
    mid=QColor("#b4b4b4"),
    midlight=QColor("#d2d2d2"),
    dark=QColor("#8c8c8c"),
    link=QColor("#2a82da"),
    tooltip_base=QColor("#ffffdc"),
    tooltip_text=QColor("#1e1e1e"),
)

NORD = Theme(
    id="nord",
    name="Nord",
    is_dark=True,
    pygments_style="nord",
    icon_color=QColor("#d8dee9"),
    window=QColor("#2e3440"),
    window_text=QColor("#d8dee9"),
    base=QColor("#2e3440"),
    alternate_base=QColor("#3b4252"),
    text=QColor("#d8dee9"),
    button=QColor("#3b4252"),
    button_text=QColor("#d8dee9"),
    highlight=QColor("#88c0d0"),
    highlighted_text=QColor("#2e3440"),
    mid=QColor("#434c5e"),
    midlight=QColor("#3b4252"),
    dark=QColor("#81a1c1"),
    link=QColor("#88c0d0"),
    tooltip_base=QColor("#3b4252"),
    tooltip_text=QColor("#d8dee9"),
)

GRUVBOX = Theme(
    id="gruvbox",
    name="Gruvbox Dark",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor("#ebdbb2"),
    window=QColor("#282828"),
    window_text=QColor("#ebdbb2"),
    base=QColor("#282828"),
    alternate_base=QColor("#32302f"),
    text=QColor("#ebdbb2"),
    button=QColor("#3c3836"),
    button_text=QColor("#ebdbb2"),
    highlight=QColor("#458588"),
    highlighted_text=QColor("#282828"),
    mid=QColor("#504945"),
    midlight=QColor("#3c3836"),
    dark=QColor("#a89984"),
    link=QColor("#83a598"),
    tooltip_base=QColor("#32302f"),
    tooltip_text=QColor("#ebdbb2"),
)

CATPPUCCIN_MOCHA = Theme(
    id="catppuccin-mocha",
    name="Catppuccin Mocha",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor("#cdd6f4"),
    window=QColor("#1e1e2e"),
    window_text=QColor("#cdd6f4"),
    base=QColor("#1e1e2e"),
    alternate_base=QColor("#313244"),
    text=QColor("#cdd6f4"),
    button=QColor("#45475a"),
    button_text=QColor("#cdd6f4"),
    highlight=QColor("#89b4fa"),
    highlighted_text=QColor("#1e1e2e"),
    mid=QColor("#585b70"),
    midlight=QColor("#45475a"),
    dark=QColor("#89b4fa"),
    link=QColor("#89b4fa"),
    tooltip_base=QColor("#313244"),
    tooltip_text=QColor("#cdd6f4"),
)

CATPPUCCIN_LATTE = Theme(
    id="catppuccin-latte",
    name="Catppuccin Latte",
    is_dark=False,
    pygments_style="default",
    icon_color=QColor("#4c4f69"),
    window=QColor("#eff1f5"),
    window_text=QColor("#4c4f69"),
    base=QColor("#eff1f5"),
    alternate_base=QColor("#e6e9ef"),
    text=QColor("#4c4f69"),
    button=QColor("#e6e9ef"),
    button_text=QColor("#4c4f69"),
    highlight=QColor("#1e66f5"),
    highlighted_text=QColor("#eff1f5"),
    mid=QColor("#bcc0cc"),
    midlight=QColor("#ccd0da"),
    dark=QColor("#1e66f5"),
    link=QColor("#1e66f5"),
    tooltip_base=QColor("#e6e9ef"),
    tooltip_text=QColor("#4c4f69"),
)

TOKYO_NIGHT = Theme(
    id="tokyo-night",
    name="Tokyo Night",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor("#a9b1d6"),
    window=QColor("#1a1b26"),
    window_text=QColor("#a9b1d6"),
    base=QColor("#1a1b26"),
    alternate_base=QColor("#292e42"),
    text=QColor("#a9b1d6"),
    button=QColor("#292e42"),
    button_text=QColor("#a9b1d6"),
    highlight=QColor("#7aa2f7"),
    highlighted_text=QColor("#1a1b26"),
    mid=QColor("#565f89"),
    midlight=QColor("#292e42"),
    dark=QColor("#7aa2f7"),
    link=QColor("#7aa2f7"),
    tooltip_base=QColor("#292e42"),
    tooltip_text=QColor("#a9b1d6"),
)

DRACULA = Theme(
    id="dracula",
    name="Dracula",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor("#f8f8f2"),
    window=QColor("#282a36"),
    window_text=QColor("#f8f8f2"),
    base=QColor("#282a36"),
    alternate_base=QColor("#44475a"),
    text=QColor("#f8f8f2"),
    button=QColor("#44475a"),
    button_text=QColor("#f8f8f2"),
    highlight=QColor("#bd93f9"),
    highlighted_text=QColor("#282a36"),
    mid=QColor("#6272a4"),
    midlight=QColor("#44475a"),
    dark=QColor("#8be9fd"),
    link=QColor("#8be9fd"),
    tooltip_base=QColor("#44475a"),
    tooltip_text=QColor("#f8f8f2"),
)

SOLARIZED_DARK = Theme(
    id="solarized-dark",
    name="Solarized Dark",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor("#93a1a1"),
    window=QColor("#002b36"),
    window_text=QColor("#839496"),
    base=QColor("#002b36"),
    alternate_base=QColor("#073642"),
    text=QColor("#839496"),
    button=QColor("#073642"),
    button_text=QColor("#839496"),
    highlight=QColor("#268bd2"),
    highlighted_text=QColor("#002b36"),
    mid=QColor("#586e75"),
    midlight=QColor("#073642"),
    dark=QColor("#268bd2"),
    link=QColor("#268bd2"),
    tooltip_base=QColor("#073642"),
    tooltip_text=QColor("#839496"),
)

EVERFOREST = Theme(
    id="everforest",
    name="Everforest",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor("#d3c6aa"),
    window=QColor("#23282e"),
    window_text=QColor("#d3c6aa"),
    base=QColor("#23282e"),
    alternate_base=QColor("#2d3238"),
    text=QColor("#d3c6aa"),
    button=QColor("#2d3238"),
    button_text=QColor("#d3c6aa"),
    highlight=QColor("#87c07c"),
    highlighted_text=QColor("#23282e"),
    mid=QColor("#505550"),
    midlight=QColor("#2d3238"),
    dark=QColor("#87c07c"),
    link=QColor("#87c07c"),
    tooltip_base=QColor("#2d3238"),
    tooltip_text=QColor("#d3c6aa"),
)

ALL_THEMES: list[Theme] = [
    SYSTEM_LIGHT,
    NORD,
    GRUVBOX,
    CATPPUCCIN_MOCHA,
    CATPPUCCIN_LATTE,
    TOKYO_NIGHT,
    DRACULA,
    SOLARIZED_DARK,
    EVERFOREST,
]

_BY_ID: dict[str, Theme] = {t.id: t for t in ALL_THEMES}


def get_theme(theme_id: str) -> Theme:
    return _BY_ID.get(theme_id, ALL_THEMES[0])


def system_theme() -> Theme:
    """Return System theme resolved to dark or light based on OS preference."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
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
    return SYSTEM_LIGHT
