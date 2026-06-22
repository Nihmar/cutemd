"""Theme definitions — palettes and metadata for each theme."""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

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


# ---------------------------------------------------------------------------
# Built-in themes
# ---------------------------------------------------------------------------

SYSTEM = Theme(
    id="system",
    name="System",
    is_dark=False,  # determined at runtime
    pygments_style="default",
    icon_color=QColor(48, 48, 48),
    window=QColor(240, 240, 240),
    window_text=QColor(30, 30, 30),
    base=QColor(255, 255, 255),
    alternate_base=QColor(245, 245, 245),
    text=QColor(30, 30, 30),
    button=QColor(240, 240, 240),
    button_text=QColor(30, 30, 30),
    highlight=QColor(42, 130, 218),
    highlighted_text=QColor(255, 255, 255),
    mid=QColor(180, 180, 180),
    midlight=QColor(210, 210, 210),
    dark=QColor(140, 140, 140),
    link=QColor(42, 130, 218),
    tooltip_base=QColor(255, 255, 220),
    tooltip_text=QColor(30, 30, 30),
)

NORD = Theme(
    id="nord",
    name="Nord",
    is_dark=True,
    pygments_style="nord",
    icon_color=QColor(216, 222, 233),
    window=QColor(46, 52, 64),
    window_text=QColor(216, 222, 233),
    base=QColor(46, 52, 64),
    alternate_base=QColor(59, 66, 82),
    text=QColor(216, 222, 233),
    button=QColor(59, 66, 82),
    button_text=QColor(216, 222, 233),
    highlight=QColor(136, 192, 208),
    highlighted_text=QColor(46, 52, 64),
    mid=QColor(67, 76, 94),
    midlight=QColor(59, 66, 82),
    dark=QColor(129, 161, 193),
    link=QColor(136, 192, 208),
    tooltip_base=QColor(59, 66, 82),
    tooltip_text=QColor(216, 222, 233),
)

GRUVBOX = Theme(
    id="gruvbox",
    name="Gruvbox Dark",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor(235, 219, 178),
    window=QColor(40, 40, 40),
    window_text=QColor(235, 219, 178),
    base=QColor(40, 40, 40),
    alternate_base=QColor(50, 48, 47),
    text=QColor(235, 219, 178),
    button=QColor(60, 56, 54),
    button_text=QColor(235, 219, 178),
    highlight=QColor(69, 133, 136),
    highlighted_text=QColor(40, 40, 40),
    mid=QColor(80, 73, 69),
    midlight=QColor(60, 56, 54),
    dark=QColor(168, 153, 132),
    link=QColor(131, 165, 152),
    tooltip_base=QColor(50, 48, 47),
    tooltip_text=QColor(235, 219, 178),
)

CATPPUCCIN_MOCHA = Theme(
    id="catppuccin-mocha",
    name="Catppuccin Mocha",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor(205, 214, 244),
    window=QColor(30, 30, 46),
    window_text=QColor(205, 214, 244),
    base=QColor(30, 30, 46),
    alternate_base=QColor(49, 50, 68),
    text=QColor(205, 214, 244),
    button=QColor(69, 71, 90),
    button_text=QColor(205, 214, 244),
    highlight=QColor(137, 180, 250),
    highlighted_text=QColor(30, 30, 46),
    mid=QColor(88, 91, 112),
    midlight=QColor(69, 71, 90),
    dark=QColor(137, 180, 250),
    link=QColor(137, 180, 250),
    tooltip_base=QColor(49, 50, 68),
    tooltip_text=QColor(205, 214, 244),
)

CATPPUCCIN_LATTE = Theme(
    id="catppuccin-latte",
    name="Catppuccin Latte",
    is_dark=False,
    pygments_style="default",
    icon_color=QColor(76, 79, 105),
    window=QColor(239, 241, 245),
    window_text=QColor(76, 79, 105),
    base=QColor(239, 241, 245),
    alternate_base=QColor(230, 233, 239),
    text=QColor(76, 79, 105),
    button=QColor(230, 233, 239),
    button_text=QColor(76, 79, 105),
    highlight=QColor(30, 102, 245),
    highlighted_text=QColor(239, 241, 245),
    mid=QColor(188, 192, 204),
    midlight=QColor(204, 208, 218),
    dark=QColor(30, 102, 245),
    link=QColor(30, 102, 245),
    tooltip_base=QColor(230, 233, 239),
    tooltip_text=QColor(76, 79, 105),
)

TOKYO_NIGHT = Theme(
    id="tokyo-night",
    name="Tokyo Night",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor(169, 177, 214),
    window=QColor(26, 27, 38),
    window_text=QColor(169, 177, 214),
    base=QColor(26, 27, 38),
    alternate_base=QColor(41, 46, 66),
    text=QColor(169, 177, 214),
    button=QColor(41, 46, 66),
    button_text=QColor(169, 177, 214),
    highlight=QColor(122, 162, 247),
    highlighted_text=QColor(26, 27, 38),
    mid=QColor(86, 95, 137),
    midlight=QColor(41, 46, 66),
    dark=QColor(122, 162, 247),
    link=QColor(122, 162, 247),
    tooltip_base=QColor(41, 46, 66),
    tooltip_text=QColor(169, 177, 214),
)

DRACULA = Theme(
    id="dracula",
    name="Dracula",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor(248, 248, 242),
    window=QColor(40, 42, 54),
    window_text=QColor(248, 248, 242),
    base=QColor(40, 42, 54),
    alternate_base=QColor(68, 71, 90),
    text=QColor(248, 248, 242),
    button=QColor(68, 71, 90),
    button_text=QColor(248, 248, 242),
    highlight=QColor(189, 147, 249),
    highlighted_text=QColor(40, 42, 54),
    mid=QColor(98, 114, 164),
    midlight=QColor(68, 71, 90),
    dark=QColor(139, 233, 253),
    link=QColor(139, 233, 253),
    tooltip_base=QColor(68, 71, 90),
    tooltip_text=QColor(248, 248, 242),
)

SOLARIZED_DARK = Theme(
    id="solarized-dark",
    name="Solarized Dark",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor(147, 161, 161),
    window=QColor(0, 43, 54),
    window_text=QColor(131, 148, 150),
    base=QColor(0, 43, 54),
    alternate_base=QColor(7, 54, 66),
    text=QColor(131, 148, 150),
    button=QColor(7, 54, 66),
    button_text=QColor(131, 148, 150),
    highlight=QColor(38, 139, 210),
    highlighted_text=QColor(0, 43, 54),
    mid=QColor(88, 110, 117),
    midlight=QColor(7, 54, 66),
    dark=QColor(38, 139, 210),
    link=QColor(38, 139, 210),
    tooltip_base=QColor(7, 54, 66),
    tooltip_text=QColor(131, 148, 150),
)

EVERFOREST = Theme(
    id="everforest",
    name="Everforest",
    is_dark=True,
    pygments_style="monokai",
    icon_color=QColor(211, 198, 170),
    window=QColor(35, 40, 46),
    window_text=QColor(211, 198, 170),
    base=QColor(35, 40, 46),
    alternate_base=QColor(45, 50, 56),
    text=QColor(211, 198, 170),
    button=QColor(45, 50, 56),
    button_text=QColor(211, 198, 170),
    highlight=QColor(135, 192, 124),
    highlighted_text=QColor(35, 40, 46),
    mid=QColor(80, 85, 80),
    midlight=QColor(45, 50, 56),
    dark=QColor(135, 192, 124),
    link=QColor(135, 192, 124),
    tooltip_base=QColor(45, 50, 56),
    tooltip_text=QColor(211, 198, 170),
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_THEMES: list[Theme] = [
    SYSTEM,
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
    return _BY_ID.get(theme_id, SYSTEM)


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
    return SYSTEM
