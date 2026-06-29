"""Tests for core/link_resolution.py"""

from core.link_resolution import build_line_anchor_map
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from markdown.math_renderers import (
    render_math_inline, render_math_inline_double,
    render_math_block, render_math_block_label,
)
from markdown.tools import highlight_code


def _make_parser():
    md = (
        MarkdownIt("commonmark", {"highlight": highlight_code})
        .enable(["table", "strikethrough"])
        .use(dollarmath_plugin)
    )
    md.renderer.rules["math_inline"] = render_math_inline
    md.renderer.rules["math_inline_double"] = render_math_inline_double
    md.renderer.rules["math_block"] = render_math_block
    md.renderer.rules["math_block_label"] = render_math_block_label
    return md


def test_line_anchor_map_simple():
    md = _make_parser()
    text = "# H1\nline1\n## H2\nline2\n### H3\nline3"
    result = build_line_anchor_map(md, text)
    assert len(result) == 6
    assert result[0] >= 0  # heading h1 anchor
    assert result[2] >= 0  # heading h2 anchor
    assert result[4] >= 0  # heading h3 anchor


def test_line_anchor_map_no_headings():
    md = _make_parser()
    text = "plain text\nmore text"
    result = build_line_anchor_map(md, text)
    assert len(result) == 2
