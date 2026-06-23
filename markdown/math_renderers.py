"""Math renderers for the dollarmath markdown-it plugin.

Two strategies, chosen by the caller:

1. `render_math_*` — MathML (via latex2mathml).  Renders natively in
   Chromium — instant, offline, no CDN.  Good for editing.

2. `render_math_*_latex` — LaTeX delimiters for MathJax.  Book-quality
   typography but requires CDN and JavaScript processing.
"""

import xml.etree.ElementTree as ET

from latex2mathml.converter import convert as _tex2mathml


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# MathML renderers (instant, offline, native Chromium rendering)
# ---------------------------------------------------------------------------


def _tex_to_mathml(tex: str, display: str) -> str:
    """Convert LaTeX to MathML HTML.  Chromium renderizza nativamente."""
    try:
        mathml_str = _tex2mathml(tex, display=display)
        # Strip outer <math ...> from latex2mathml
        inner = mathml_str
        if inner.startswith("<math"):
            gt = inner.find(">")
            if gt != -1:
                inner = inner[gt + 1 :]
            if inner.endswith("</math>"):
                inner = inner[:-7]
            inner = inner.strip()

        if display == "block":
            return f'<div class="math-block"><math display="block">{inner}</math></div>'
        else:
            return f'<math class="math-inline" display="inline">{inner}</math>'
    except Exception:
        escaped = _escape_html(tex)
        if display == "block":
            return f'<pre class="math-block-fallback">$$\n{escaped}\n$$</pre>'
        return f'<span class="math-inline-fallback">${escaped}$</span>'


def render_math_inline(tokens, idx, options, env):
    return _tex_to_mathml(tokens[idx].content, "inline")


def render_math_inline_double(tokens, idx, options, env):
    return _tex_to_mathml(tokens[idx].content, "inline")


def render_math_block(tokens, idx, options, env):
    return _tex_to_mathml(tokens[idx].content.strip(), "block")


def render_math_block_label(tokens, idx, options, env):
    return _tex_to_mathml(tokens[idx].content.strip(), "block")


# ---------------------------------------------------------------------------
# LaTeX delimiters renderers (for MathJax enhancement)
# ---------------------------------------------------------------------------


def _tex_delimited(tex: str, display: str) -> str:
    if display == "block":
        return f'<div class="math-block">\\[{tex}\\]</div>'
    else:
        return f"\\({tex}\\)"


def render_math_inline_latex(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content, "inline")


def render_math_inline_double_latex(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content, "inline")


def render_math_block_latex(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content.strip(), "block")


def render_math_block_label_latex(tokens, idx, options, env):
    return _tex_delimited(tokens[idx].content.strip(), "block")
