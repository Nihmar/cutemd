"""Build the final HTML document served to QTextBrowser."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from markdown.tools import BLOCK_OPEN_TYPES, add_heading_ids
from ui.preview_browser import add_img_dimensions, fix_image_paragraphs

if TYPE_CHECKING:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token

_WIKILINK_IMG_RE = re.compile(r"!\[\[([^\]]+?)(?:\|([^\]]*?))?\]\]")


def preprocess_wikilink_images(text: str) -> str:
    """Convert ![[wikilink]] image syntax to standard Markdown ![](...)."""
    def _repl(m: re.Match) -> str:
        target = m.group(1).strip()
        alt = m.group(2).strip() if m.group(2) else target
        return f"![{alt}]({target})"
    return _WIKILINK_IMG_RE.sub(_repl, text)


def render_with_anchors(text: str, md: MarkdownIt) -> str:
    """Render markdown to HTML with <a name='bN'> anchors inside each block."""
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
) -> str:
    """Build the complete HTML document for the preview pane."""
    try:
        body_html = add_heading_ids(render_with_anchors(text, md))
    except Exception:
        body_html = (
            "<pre>"
            + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</pre>"
        )

    body_html = add_img_dimensions(body_html, base_dir, max_width)
    body_html = fix_image_paragraphs(body_html)

    theme_class = "dark" if theme == "dark" else "light"
    font_style = f"font-size: {font_size}px;"
    if font_family != "Sistema":
        font_style += f" font-family: {font_family};"

    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n"
        "<meta charset='utf-8'>\n"
        f"<style>\n{preview_css}\n</style>\n"
        "</head>\n"
        f"<body class='{theme_class}' style='{font_style}'>\n"
        f"{body_html}\n"
        "</body>\n</html>"
    )
