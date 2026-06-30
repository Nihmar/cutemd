"""Math renderers for the dollarmath markdown-it plugin.

Outputs light placeholder spans with raw LaTeX as visible fallback.
KaTeX (injected client-side via IntersectionObserver) replaces them
with proper rendered math when scrolled into view.
"""


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tex_to_html(tex: str, display: str) -> str:
    """Return a placeholder span with raw LaTeX fallback + data-latex for KaTeX."""
    escaped = _escape_html(tex)
    if display == "block":
        delim = "$$"
        cls = "math-block"
    else:
        delim = "$"
        cls = "math-inline"
    return (
        f'<span class="{cls} math-katex"'
        f' data-latex="{escaped}">'
        f"{delim}{escaped}{delim}"
        f"</span>"
    )


def render_math_inline(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content, "inline")


def render_math_inline_double(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content, "inline")


def render_math_block(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content.strip(), "block")


def render_math_block_label(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content.strip(), "block")
