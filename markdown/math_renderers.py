"""Math renderers for the dollarmath markdown-it plugin.

Outputs LaTeX delimiters for MathJax rendering in QWebEngineView.
MathJax provides book-quality math typography (native MathML in
Chromium is functional but doesn't look like printed LaTeX).

Fallback: if MathJax doesn't load (offline), the CSS styles the raw
LaTeX as monospace text.
"""


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tex_delimited(tex: str, display: str) -> str:
    """Wrap LaTeX in MathJax-compatible delimiters."""
    if display == "block":
        return f'<div class="math-block">\\[{tex}\\]</div>'
    else:
        return f"\\({tex}\\)"


def render_math_inline(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content, "inline")


def render_math_inline_double(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content, "inline")


def render_math_block(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content.strip(), "block")


def render_math_block_label(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content.strip(), "block")
