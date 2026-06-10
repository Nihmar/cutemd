"""Markdown-to-HTML helpers: code highlighting, heading IDs, anchor types."""

import re

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

import ui.themes

# ---------------------------------------------------------------------------
# Token types that start a visible block-level element in the rendered HTML.
# We inject an <a name='bN'> anchor before each so the preview can scroll
# to the exact corresponding content.
# ---------------------------------------------------------------------------
BLOCK_OPEN_TYPES = frozenset(
    {
        "heading_open",
        "paragraph_open",
        "fence",
        "blockquote_open",
        "bullet_list_open",
        "ordered_list_open",
        "table_open",
        "hr",
        "math_block",
        "math_block_label",
        "html_block",
    }
)


def highlight_code(code: str, lang: str, _attrs: str) -> str:
    """markdown-it-py highlight callback using Pygments with inline styles."""
    lexer = None
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except ClassNotFound:
            pass
    if lexer is None:
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            lexer = get_lexer_by_name("text", stripall=True)

    formatter = HtmlFormatter(
        style=ui.themes.PYGMENTS_STYLE, noclasses=True, nowrap=True
    )
    return highlight(code, lexer, formatter)


def _slugify(text: str) -> str:
    """Generate an HTML anchor slug from heading text."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


_HEADING_TAG_RE = re.compile(r"<(h[1-6])>(.*?)</\1>", re.DOTALL)


def add_heading_ids(html: str) -> str:
    """Post-process HTML to add id attributes on heading tags."""

    def _replacer(m: re.Match) -> str:
        tag = m.group(1)
        inner = m.group(2)
        plain = re.sub(r"<[^>]+>", "", inner)
        return f'<{tag} id="{_slugify(plain)}">{inner}</{tag}>'

    return _HEADING_TAG_RE.sub(_replacer, html)
