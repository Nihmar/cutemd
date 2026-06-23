"""Math renderers for the dollarmath markdown-it plugin.

Outputs LaTeX delimiters for MathJax rendering (book-quality typography).
MathML fallback is available but not used by default.
"""


def _tex_delimited(tex: str, display: str) -> str:
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
