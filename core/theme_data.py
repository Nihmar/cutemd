"""Pure theme data definitions — no Qt imports, hex strings only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeData:
    id: str
    name: str
    is_dark: bool
    pygments_style: str
    icon_color: str  # hex
    window: str
    window_text: str
    base: str
    alternate_base: str
    text: str
    button: str
    button_text: str
    highlight: str
    highlighted_text: str
    mid: str
    midlight: str
    dark: str
    link: str
    tooltip_base: str
    tooltip_text: str


SYSTEM_LIGHT = ThemeData(
    id="system",
    name="System",
    is_dark=False,
    pygments_style="default",
    icon_color="#303030",
    window="#f0f0f0",
    window_text="#1e1e1e",
    base="#ffffff",
    alternate_base="#f5f5f5",
    text="#1e1e1e",
    button="#f0f0f0",
    button_text="#1e1e1e",
    highlight="#2a82da",
    highlighted_text="#ffffff",
    mid="#b4b4b4",
    midlight="#d2d2d2",
    dark="#8c8c8c",
    link="#2a82da",
    tooltip_base="#ffffdc",
    tooltip_text="#1e1e1e",
)

NORD = ThemeData(
    id="nord",
    name="Nord",
    is_dark=True,
    pygments_style="nord",
    icon_color="#d8dee9",
    window="#2e3440",
    window_text="#d8dee9",
    base="#2e3440",
    alternate_base="#3b4252",
    text="#d8dee9",
    button="#3b4252",
    button_text="#d8dee9",
    highlight="#88c0d0",
    highlighted_text="#2e3440",
    mid="#434c5e",
    midlight="#3b4252",
    dark="#81a1c1",
    link="#88c0d0",
    tooltip_base="#3b4252",
    tooltip_text="#d8dee9",
)

GRUVBOX = ThemeData(
    id="gruvbox",
    name="Gruvbox Dark",
    is_dark=True,
    pygments_style="monokai",
    icon_color="#ebdbb2",
    window="#282828",
    window_text="#ebdbb2",
    base="#282828",
    alternate_base="#32302f",
    text="#ebdbb2",
    button="#3c3836",
    button_text="#ebdbb2",
    highlight="#458588",
    highlighted_text="#282828",
    mid="#504945",
    midlight="#3c3836",
    dark="#a89984",
    link="#83a598",
    tooltip_base="#32302f",
    tooltip_text="#ebdbb2",
)

CATPPUCCIN_MOCHA = ThemeData(
    id="catppuccin-mocha",
    name="Catppuccin Mocha",
    is_dark=True,
    pygments_style="monokai",
    icon_color="#cdd6f4",
    window="#1e1e2e",
    window_text="#cdd6f4",
    base="#1e1e2e",
    alternate_base="#313244",
    text="#cdd6f4",
    button="#45475a",
    button_text="#cdd6f4",
    highlight="#89b4fa",
    highlighted_text="#1e1e2e",
    mid="#585b70",
    midlight="#45475a",
    dark="#89b4fa",
    link="#89b4fa",
    tooltip_base="#313244",
    tooltip_text="#cdd6f4",
)

CATPPUCCIN_LATTE = ThemeData(
    id="catppuccin-latte",
    name="Catppuccin Latte",
    is_dark=False,
    pygments_style="default",
    icon_color="#4c4f69",
    window="#eff1f5",
    window_text="#4c4f69",
    base="#eff1f5",
    alternate_base="#e6e9ef",
    text="#4c4f69",
    button="#e6e9ef",
    button_text="#4c4f69",
    highlight="#1e66f5",
    highlighted_text="#eff1f5",
    mid="#bcc0cc",
    midlight="#ccd0da",
    dark="#1e66f5",
    link="#1e66f5",
    tooltip_base="#e6e9ef",
    tooltip_text="#4c4f69",
)

TOKYO_NIGHT = ThemeData(
    id="tokyo-night",
    name="Tokyo Night",
    is_dark=True,
    pygments_style="monokai",
    icon_color="#a9b1d6",
    window="#1a1b26",
    window_text="#a9b1d6",
    base="#1a1b26",
    alternate_base="#292e42",
    text="#a9b1d6",
    button="#292e42",
    button_text="#a9b1d6",
    highlight="#7aa2f7",
    highlighted_text="#1a1b26",
    mid="#565f89",
    midlight="#292e42",
    dark="#7aa2f7",
    link="#7aa2f7",
    tooltip_base="#292e42",
    tooltip_text="#a9b1d6",
)

DRACULA = ThemeData(
    id="dracula",
    name="Dracula",
    is_dark=True,
    pygments_style="monokai",
    icon_color="#f8f8f2",
    window="#282a36",
    window_text="#f8f8f2",
    base="#282a36",
    alternate_base="#44475a",
    text="#f8f8f2",
    button="#44475a",
    button_text="#f8f8f2",
    highlight="#bd93f9",
    highlighted_text="#282a36",
    mid="#6272a4",
    midlight="#44475a",
    dark="#8be9fd",
    link="#8be9fd",
    tooltip_base="#44475a",
    tooltip_text="#f8f8f2",
)

SOLARIZED_DARK = ThemeData(
    id="solarized-dark",
    name="Solarized Dark",
    is_dark=True,
    pygments_style="monokai",
    icon_color="#93a1a1",
    window="#002b36",
    window_text="#839496",
    base="#002b36",
    alternate_base="#073642",
    text="#839496",
    button="#073642",
    button_text="#839496",
    highlight="#268bd2",
    highlighted_text="#002b36",
    mid="#586e75",
    midlight="#073642",
    dark="#268bd2",
    link="#268bd2",
    tooltip_base="#073642",
    tooltip_text="#839496",
)

EVERFOREST = ThemeData(
    id="everforest",
    name="Everforest",
    is_dark=True,
    pygments_style="monokai",
    icon_color="#d3c6aa",
    window="#23282e",
    window_text="#d3c6aa",
    base="#23282e",
    alternate_base="#2d3238",
    text="#d3c6aa",
    button="#2d3238",
    button_text="#d3c6aa",
    highlight="#87c07c",
    highlighted_text="#23282e",
    mid="#505550",
    midlight="#2d3238",
    dark="#87c07c",
    link="#87c07c",
    tooltip_base="#2d3238",
    tooltip_text="#d3c6aa",
)

ALL_THEMES_DATA: list[ThemeData] = [
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

_BY_ID: dict[str, ThemeData] = {t.id: t for t in ALL_THEMES_DATA}


def get_theme_data(theme_id: str) -> ThemeData:
    return _BY_ID.get(theme_id, SYSTEM_LIGHT)
