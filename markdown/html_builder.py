"""Build the final HTML document served to QTextBrowser."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from markdown.image_utils import SizeProvider, add_img_dimensions, fix_image_paragraphs
from markdown.tools import BLOCK_OPEN_TYPES, add_heading_ids

if TYPE_CHECKING:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token

_WIKILINK_IMG_RE = re.compile(r"!\[\[([^\]]+?)(?:\|([^\]]*?))?\]\]")
_WIKILINK_RE = re.compile(r"(?<!\!)\[\[([^\]]+)\]\]")

# Per normalizzare border="0" → border="1" su <table>, inclusi inline HTML.
_TABLE_TAG_RE = re.compile(r"<table\b([^>]*)>", re.IGNORECASE)
_TABLE_BORDER_ATTR_RE = re.compile(r'\s+border="[^"]*"', re.IGNORECASE)


def _fix_table_tag(m: re.Match) -> str:
    """Ensure every <table> has border="1", preserving original case."""
    full = m.group(0)
    attrs = m.group(1)
    # Reconstruct from original match to preserve case.
    tag_name = full[:6]  # '<table' (whatever case)
    close = ">"
    # Remove any existing border attribute.
    attrs = _TABLE_BORDER_ATTR_RE.sub("", attrs)
    return f'{tag_name}{attrs} border="1"{close}'


def preprocess_wikilink_images(text: str) -> str:
    def _repl(m: re.Match) -> str:
        target = m.group(1).strip()
        alt = m.group(2).strip() if m.group(2) else target
        return f"![{alt}]({target})"

    return _WIKILINK_IMG_RE.sub(_repl, text)


def preprocess_wikilinks(text: str) -> str:
    """Convert [[file]] and [[display|file]] to standard Markdown links."""

    def _repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        if "|" in inner:
            display, _, target = inner.partition("|")
            return f"[{display.strip()}]({target.strip()})"
        return f"[{inner}]({inner})"

    return _WIKILINK_RE.sub(_repl, text)


def render_with_anchors(text: str, md: MarkdownIt) -> str:
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
                anchor.content = f'<a name="b{anchor_idx}"></a>'
                new_tokens.append(anchor)
                anchor_idx += 1
    return md.renderer.render(new_tokens, md.options, {})


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
    images_dir: Path | None = None,
) -> str:
    try:
        body_html = add_heading_ids(render_with_anchors(text, md))
    except Exception:
        body_html = (
            "<pre>"
            + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</pre>"
        )

    body_html = add_img_dimensions(
        body_html, base_dir, max_width, get_image_size, images_dir
    )
    body_html = fix_image_paragraphs(body_html)

    # Qt ignora border CSS su th/td ma usa l'attributo border del <table>.
    # markdown-it emette border="0", tabelle HTML inline non hanno border.
    # Rimuoviamo eventuali border esistenti e imponiamo border="1" ovunque.
    body_html = _TABLE_TAG_RE.sub(_fix_table_tag, body_html)

    theme_class = "dark" if theme == "dark" else "light"

    # Qt non supporta px per font-size — usa pt.
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

    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n"
        "<meta charset='utf-8'>\n"
        f"<style>\n{font_body_css}\n{preview_css}\n</style>\n"
        "</head>\n"
        f"<body class='{theme_class}'>\n"
        f"{body_html}\n"
        "</body>\n</html>"
    )
