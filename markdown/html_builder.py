"""Build the final HTML document served to QTextBrowser."""

from __future__ import annotations

import base64
import re
from html import unescape as _unescape_html
from pathlib import Path
from typing import TYPE_CHECKING

from markdown.image_utils import (
    SizeProvider,
    add_img_dimensions,
    build_file_index,
    fix_image_paragraphs,
)

from core.logging import setup_logging

_LOG = setup_logging("cutemd.html_builder")
from markdown.tools import BLOCK_OPEN_TYPES, add_heading_ids

if TYPE_CHECKING:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token

_WIKILINK_IMG_RE = re.compile(r"!\[\[([^\]]+?)(?:\|([^\]]*?))?\]\]")
_WIKILINK_RE = re.compile(r"(?<!\!)\[\[([^\]]+)\]\]")

_TABLE_TAG_RE = re.compile(r"<table\b([^>]*)>", re.IGNORECASE)
_TABLE_BORDER_ATTR_RE = re.compile(r'\s+border="[^"]*"', re.IGNORECASE)

_IMG_FILE_URL_RE = re.compile(r'<img\s[^>]*\bsrc="(file:///[^"]+)"[^>]*>')
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n(?:---|\.\.\.)\s*\n", re.DOTALL)

# Inline #tag (not at line start to avoid matching headings)
_INLINE_TAG_RE = re.compile(r"(?<=\s)#([\w\u0080-\uFFFF][\w\u0080-\uFFFF-]*)")

_CODE_BLOCK_RE = re.compile(
    r"(<pre><code[^>]*>)(.*?)(</code></pre>)", re.DOTALL
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")

# Cache for build_file_index — invalidated by vault root mtime.
_FILE_INDEX_CACHE: dict[Path, tuple[float, dict[str, list[Path]]]] = {}


def _fix_table_tag(m: re.Match) -> str:
    """Ensure every <table> has border="1", preserving original case."""
    full = m.group(0)
    attrs = m.group(1)
    tag_name = full[:6]
    close = ">"
    attrs = _TABLE_BORDER_ATTR_RE.sub("", attrs)
    return f'{tag_name}{attrs} border="1"{close}'


def _inject_copy_buttons(html: str) -> str:
    def _replace(m: re.Match) -> str:
        open_tag = m.group(1)
        inner = m.group(2)
        close_tag = m.group(3)
        raw = _unescape_html(_TAG_STRIP_RE.sub("", inner))
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
        copy_link = (
            '<p style="text-align:right;margin:2px 0;font-size:12px;">'
            f'<a href="http://cutemd-copy/{encoded}" '
            'style="text-decoration:none;">📋 Copy</a></p>'
        )
        return f"{copy_link}{open_tag}{inner}{close_tag}"
    return _CODE_BLOCK_RE.sub(_replace, html)


def preprocess_wikilink_images(text: str) -> str:
    def _repl(m: re.Match) -> str:
        target = m.group(1).strip()
        alt = m.group(2).strip() if m.group(2) else target
        from urllib.parse import quote as _uq
        return f"![{alt}]({_uq(target, safe='/')})"
    return _WIKILINK_IMG_RE.sub(_repl, text)


def preprocess_wikilinks(text: str) -> str:
    def _repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        from urllib.parse import quote as _uq
        if "|" in inner:
            display, _, target = inner.partition("|")
            return f"[{display.strip()}]({_uq(target.strip(), safe='/')})"
        return f"[{inner}]({_uq(inner, safe='/')})"
    return _WIKILINK_RE.sub(_repl, text)


def preprocess_tags(text: str) -> str:
    """Wrap inline ``#tag`` tokens in ``<span style="...">`` for styling."""
    result = _INLINE_TAG_RE.sub(
        r'<span style="color:#d19a66;font-weight:bold">#\1</span>', text
    )
    if result != text:
        _LOG.debug("preprocess_tags: %d tag(s) wrapped",
                   len(_INLINE_TAG_RE.findall(text)))
    return result


def strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def render_with_anchors(text: str, md: MarkdownIt, frontmatter_offset: int = 0) -> str:
    from markdown_it.token import Token
    tokens: list[Token] = md.parse(text)
    new_tokens: list[Token] = []
    anchor_idx = 0
    for token in tokens:
        new_tokens.append(token)
        if token.type in BLOCK_OPEN_TYPES and token.map:
            start, end = token.map
            if start < end:
                anchor = Token("html_inline", "", 0)
                anchor.content = (
                    f'<a name="b{anchor_idx}" data-line="{start + frontmatter_offset}"></a>'
                )
                new_tokens.append(anchor)
                anchor_idx += 1
    return md.renderer.render(new_tokens, md.options, {})


def _cached_file_index(vault_root: Path) -> dict[str, list[Path]]:
    """Return a cached file index, invalidated by vault root mtime."""
    try:
        mtime = vault_root.stat().st_mtime
    except OSError:
        return build_file_index(vault_root)
    cached = _FILE_INDEX_CACHE.get(vault_root)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    idx = build_file_index(vault_root)
    _FILE_INDEX_CACHE[vault_root] = (mtime, idx)
    return idx


def _lighten(hex_color: str, factor: float = 0.3) -> str:
    """Lighten a hex color by blending with white."""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color: str, factor: float = 0.3) -> str:
    """Darken a hex color by blending with black."""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def build_html(
    *,
    text: str,
    md: MarkdownIt,
    preview_css: str,
    theme: str,
    font_family: str,
    font_size: int,
    base_dir: Path,
    max_width: int,
    get_image_size: SizeProvider,
    attachments_dir: Path | None = None,
    theme_bg: str = "",
    theme_fg: str = "",
    theme_mid: str = "",
    frontmatter_offset: int = 0,
) -> str:
    try:
        body_html = add_heading_ids(render_with_anchors(text, md, frontmatter_offset))
    except Exception:
        body_html = (
            "<pre>"
            + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</pre>"
        )

    # Build a file index once for the vault root.
    vault_root = attachments_dir.parent if attachments_dir is not None else base_dir
    file_index = _cached_file_index(vault_root)

    body_html = add_img_dimensions(
        body_html, base_dir, max_width, get_image_size, attachments_dir, file_index
    )
    body_html = fix_image_paragraphs(body_html)

    body_html = _TABLE_TAG_RE.sub(_fix_table_tag, body_html)
    body_html = _IMG_FILE_URL_RE.sub(r'<a href="\1">\g<0></a>', body_html)
    body_html = _inject_copy_buttons(body_html)

    theme_class = "dark" if theme == "dark" else "light"

    font_body_css = f"body {{ font-size: {font_size}pt; }}"
    if font_family not in ("System", "Sistema"):
        if " " in font_family:
            font_body_css = (
                f'body {{ font-family: "{font_family}"; font-size: {font_size}pt; }}'
            )
        else:
            font_body_css = (
                f"body {{ font-family: {font_family}; font-size: {font_size}pt; }}"
            )

    # Theme-specific background/text overrides (from Qt palette).
    # Must use "body.theme_class" to override the defaults in preview_css
    # which also use "body.dark" / "body.light" (same specificity).
    theme_override = ""
    if theme_bg:
        theme_override += f"\nbody.{theme_class} {{ background-color: {theme_bg}; }}"
    if theme_fg:
        theme_override += f"\nbody.{theme_class} {{ color: {theme_fg}; }}"

    # Scrollbar styling to match the theme palette.
    if theme_bg and theme_mid:
        thumb_hover = _lighten(theme_mid) if theme == "dark" else _darken(theme_mid)
        theme_override += (
            f"\n::-webkit-scrollbar {{ width: 10px; height: 10px; }}"
            f"\n::-webkit-scrollbar-track {{ background: {theme_bg}; }}"
            f"\n::-webkit-scrollbar-thumb {{ background: {theme_mid}; border-radius: 5px; }}"
            f"\n::-webkit-scrollbar-thumb:hover {{ background: {thumb_hover}; }}"
            f"\n::-webkit-scrollbar-corner {{ background: {theme_bg}; }}"
        )

    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n"
        "<meta charset='utf-8'>\n"
        f"<style>\n{font_body_css}\n{preview_css}{theme_override}\n</style>\n"
        "</head>\n"
        f"<body class='{theme_class}'>\n"
        f"{body_html}\n"
        "</body>\n</html>"
    )
