"""Build the final HTML document served to QTextBrowser."""

from __future__ import annotations

import base64
import re
from html import unescape as _unescape_html
from pathlib import Path
from typing import TYPE_CHECKING

from markdown.image_utils import SizeProvider, add_img_dimensions, build_file_index, fix_image_paragraphs
from markdown.tools import BLOCK_OPEN_TYPES, add_heading_ids

if TYPE_CHECKING:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token

_WIKILINK_IMG_RE = re.compile(r"!\[\[([^\]]+?)(?:\|([^\]]*?))?\]\]")
_WIKILINK_RE = re.compile(r"(?<!\!)\[\[([^\]]+)\]\]")

# Per normalizzare border="0" → border="1" su <table>, inclusi inline HTML.
_TABLE_TAG_RE = re.compile(r"<table\b([^>]*)>", re.IGNORECASE)
_TABLE_BORDER_ATTR_RE = re.compile(r'\s+border="[^"]*"', re.IGNORECASE)

# Wrap resolved <img src="file:///..."> in a clickable <a>.
_IMG_FILE_URL_RE = re.compile(r'<img\s[^>]*\bsrc="(file:///[^"]+)"[^>]*>')
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n(?:---|\.\.\.)\s*\n", re.DOTALL)

# Match fenced code blocks for copy-button injection.
_CODE_BLOCK_RE = re.compile(
    r"(<pre><code[^>]*>)(.*?)(</code></pre>)", re.DOTALL
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


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


def _inject_copy_buttons(html: str) -> str:
    """Wrap every fenced code block with a \"Copy\" link.

    QTextBrowser does not support JavaScript, so we inject a clickable
    anchor.  Qt's rich-text renderer treats any ``http://`` URL as a
    clickable link, so we use ``http://cutemd-copy/`` as a pseudo-scheme
    carrying the raw code (URL-safe base64 encoded).  The
    ``PreviewTextBrowser`` intercepts the link before external-browser
    dispatch and writes the decoded text to the system clipboard.
    """

    def _replace(m: re.Match) -> str:
        open_tag = m.group(1)
        inner = m.group(2)
        close_tag = m.group(3)

        # Strip HTML tags and decode entities to recover raw source.
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
    """Convert [[file]] and [[display|file]] to standard Markdown links."""

    def _repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        from urllib.parse import quote as _uq
        if "|" in inner:
            display, _, target = inner.partition("|")
            return f"[{display.strip()}]({_uq(target.strip(), safe='/')})"
        return f"[{inner}]({_uq(inner, safe='/')})"

    return _WIKILINK_RE.sub(_repl, text)


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from the beginning of *text*."""
    return _FRONTMATTER_RE.sub("", text, count=1)


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
    attachments_dir: Path | None = None,
) -> str:
    try:
        body_html = add_heading_ids(render_with_anchors(text, md))
    except Exception:
        body_html = (
            "<pre>"
            + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</pre>"
        )

    # Build a file index once for the vault root so image resolution
    # doesn't do a full rglob per unresolved image.
    vault_root = attachments_dir.parent if attachments_dir is not None else base_dir
    file_index = build_file_index(vault_root)

    body_html = add_img_dimensions(
        body_html, base_dir, max_width, get_image_size, attachments_dir, file_index
    )
    body_html = fix_image_paragraphs(body_html)

    # Qt ignora border CSS su th/td ma usa l'attributo border del <table>.
    # markdown-it emette border="0", tabelle HTML inline non hanno border.
    # Rimuoviamo eventuali border esistenti e imponiamo border="1" ovunque.
    body_html = _TABLE_TAG_RE.sub(_fix_table_tag, body_html)

    # Rende le immagini cliccabili: wrap <img src="file:///..."> in <a href="...">
    body_html = _IMG_FILE_URL_RE.sub(r'<a href="\1">\g<0></a>', body_html)

    # Inject "Copy" links on code blocks.
    body_html = _inject_copy_buttons(body_html)

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
