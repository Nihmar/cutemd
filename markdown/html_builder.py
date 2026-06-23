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


def preprocess_wikilink_images(text: str) -> str:
    def _repl(m: re.Match) -> str:
        target = m.group(1).strip()
        alt = m.group(2).strip() if m.group(2) else target
        return f"![{alt}]({target})"

    text = _WIKILINK_IMG_RE.sub(_repl, text)

    # Strip YAML front matter (--- ... ---) at the beginning of the file
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3 :].lstrip("\n")

    return text


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


_MATHJAX_HEAD = (
    "<script>\n"
    "MathJax = {\n"
    "  tex: {\n"
    "    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],\n"
    "    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],\n"
    "    processEscapes: true,\n"
    "  },\n"
    "  options: {\n"
    "    ignoreHtmlClass: 'math-fallback',\n"
    "    enableEnrichment: false,\n"
    "  },\n"
    "  chtml: {\n"
    "    displayAlign: 'center',\n"
    "    displayIndent: '0',\n"
    "  },\n"
    "};\n"
    "</script>\n"
    '<script id="MathJax-script" async'
    ' src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js">'
    "</script>\n"
)


def _render_body(
    *,
    text: str,
    md: MarkdownIt,
    theme: str,
    font_family: str,
    font_size: int,
    base_dir: Path,
    max_width: int = 800,
    get_image_size: SizeProvider | None = None,
) -> tuple[str, str, str]:
    """Return (body_inner_html, theme_class, font_style)."""
    try:
        body_html = add_heading_ids(render_with_anchors(text, md))
    except Exception:
        body_html = (
            "<pre>"
            + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</pre>"
        )

    if get_image_size is not None:
        body_html = add_img_dimensions(body_html, base_dir, max_width, get_image_size)
    body_html = fix_image_paragraphs(body_html)

    theme_class = "dark" if theme == "dark" else "light"
    font_style = f"font-size: {font_size}px;"
    if font_family != "Sistema":
        font_style += f" font-family: {font_family};"

    return body_html, theme_class, font_style


def build_html(
    *,
    text: str,
    md: MarkdownIt,
    preview_css: str,
    theme: str,
    font_family: str,
    font_size: int,
    base_dir: Path,
    max_width: int = 800,
    get_image_size: SizeProvider | None = None,
) -> str:
    """Build the complete HTML document (CSS + MathJax + body)."""
    body_html, theme_class, font_style = _render_body(
        text=text,
        md=md,
        theme=theme,
        font_family=font_family,
        font_size=font_size,
        base_dir=base_dir,
        max_width=max_width,
        get_image_size=get_image_size,
    )
    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n"
        "<meta charset='utf-8'>\n"
        f"<style>\n{preview_css}\n</style>\n" + _MATHJAX_HEAD + "</head>\n"
        f"<body class='{theme_class}' style='{font_style}'>\n"
        f"{body_html}\n"
        "</body>\n</html>"
    )


def build_body_html(
    *,
    text: str,
    md: MarkdownIt,
    theme: str,
    font_family: str,
    font_size: int,
    base_dir: Path,
    max_width: int = 800,
    get_image_size: SizeProvider | None = None,
) -> tuple[str, str, str]:
    """Return (body_inner_html, theme_class, font_style) for incremental updates.

    Use this after the first full-page load to avoid re-sending CSS and
    MathJax scripts.  The caller should update the DOM via JavaScript and
    then call MathJax.typesetPromise() on the new content.
    """
    return _render_body(
        text=text,
        md=md,
        theme=theme,
        font_family=font_family,
        font_size=font_size,
        base_dir=base_dir,
        max_width=max_width,
        get_image_size=get_image_size,
    )
