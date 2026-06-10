"""Math renderers for the dollarmath markdown-it plugin.

Each function receives a token list, index, options dict, and environment,
and returns an HTML string.
"""

from latex2mathml.converter import convert as _tex2mathml


def render_math_inline(tokens, idx, options, env):
    """Render inline math $...$ as MathML."""
    content = tokens[idx].content
    try:
        return _tex2mathml(content, display="inline")
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<span class="math-inline">${escaped}$</span>'


def render_math_inline_double(tokens, idx, options, env):
    """Render inline double math $$...$$ as MathML."""
    content = tokens[idx].content
    try:
        return _tex2mathml(content, display="inline")
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<span class="math-inline">$${escaped}$$</span>'


def render_math_block(tokens, idx, options, env):
    """Render display math $$...$$ as a MathML block."""
    content = tokens[idx].content.strip()
    try:
        mathml = _tex2mathml(content, display="block")
        return f'<div class="math-block">{mathml}</div>'
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<pre class="math-block">$$\n{escaped}\n$$</pre>'


def render_math_block_label(tokens, idx, options, env):
    """Render labeled display math as a MathML block."""
    content = tokens[idx].content.strip()
    try:
        mathml = _tex2mathml(content, display="block")
        return f'<div class="math-block">{mathml}</div>'
    except Exception:
        escaped = (
            content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f'<pre class="math-block">$$\n{escaped}\n$$</pre>'
