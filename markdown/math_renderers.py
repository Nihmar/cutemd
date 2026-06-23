"""Math renderers for the dollarmath markdown-it plugin.

Each function receives a token list, index, options dict, and environment,
and returns an HTML string suitable for QTextBrowser (no MathML support).
"""

import xml.etree.ElementTree as ET

from latex2mathml.converter import convert as _tex2mathml


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mathml_text(elem: ET.Element) -> str:
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_mathml_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _mathml_to_html(elem: ET.Element) -> str:
    """Convert a MathML element tree to styled HTML for QTextBrowser."""
    tag = elem.tag.split("}")[-1]

    if tag == "math":
        return "".join(_mathml_to_html(ch) for ch in elem)

    if tag == "mrow":
        return "".join(_mathml_to_html(ch) for ch in elem)

    if tag == "mi":
        return f'<i class="math-var">{_escape_html(_mathml_text(elem))}</i>'

    if tag == "mn":
        return f'<span class="math-num">{_escape_html(_mathml_text(elem))}</span>'

    if tag == "mo":
        return f'<span class="math-op">{_escape_html(_mathml_text(elem))}</span>'

    if tag == "mtext":
        return f'<span class="math-text">{_escape_html(_mathml_text(elem))}</span>'

    if tag == "msup":
        parts = list(elem)
        base = _mathml_to_html(parts[0]) if parts else ""
        sup = _mathml_to_html(parts[1]) if len(parts) > 1 else ""
        return f'<span class="math-sup">{base}<sup>{sup}</sup></span>'

    if tag == "msub":
        parts = list(elem)
        base = _mathml_to_html(parts[0]) if parts else ""
        sub = _mathml_to_html(parts[1]) if len(parts) > 1 else ""
        return f'<span class="math-sub">{base}<sub>{sub}</sub></span>'

    if tag == "msubsup":
        parts = list(elem)
        base = _mathml_to_html(parts[0]) if parts else ""
        sub = _mathml_to_html(parts[1]) if len(parts) > 1 else ""
        sup = _mathml_to_html(parts[2]) if len(parts) > 2 else ""
        return f'<span class="math-subsup">{base}<sub>{sub}</sub><sup>{sup}</sup></span>'

    if tag == "mfrac":
        parts = list(elem)
        num = _mathml_to_html(parts[0]) if parts else ""
        den = _mathml_to_html(parts[1]) if len(parts) > 1 else ""
        return (
            '<span class="math-frac">'
            f'<span class="math-frac-num">{num}</span>'
            f'<span class="math-frac-den">{den}</span>'
            '</span>'
        )

    if tag == "msqrt":
        inner = "".join(_mathml_to_html(ch) for ch in elem)
        return f'<span class="math-sqrt"><span class="math-sqrt-symbol">&radic;</span><span class="math-sqrt-inner">{inner}</span></span>'

    if tag == "mroot":
        parts = list(elem)
        base = _mathml_to_html(parts[0]) if parts else ""
        deg = _mathml_to_html(parts[1]) if len(parts) > 1 else ""
        return f'<span class="math-root"><sup>{deg}</sup>{base}</span>'

    if tag in ("mover", "munder", "munderover"):
        return "".join(_mathml_to_html(ch) for ch in elem)

    # Fallback: text content
    return _escape_html(_mathml_text(elem))


def _tex_to_html(tex: str, display: str) -> str:
    try:
        mathml_str = _tex2mathml(tex, display=display)
        root = ET.fromstring(mathml_str)
        inner = _mathml_to_html(root)
        cls = "math-block" if display == "block" else "math-inline"
        return f'<span class="{cls}">{inner}</span>'
    except Exception:
        escaped = _escape_html(tex)
        if display == "block":
            return f'<pre class="math-block-fallback">$$\n{escaped}\n$$</pre>'
        return f'<span class="math-inline-fallback">${escaped}$</span>'


def render_math_inline(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content, "inline")


def render_math_inline_double(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content, "inline")


def render_math_block(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content.strip(), "block")


def render_math_block_label(tokens, idx, options, env):
    return _tex_to_html(tokens[idx].content.strip(), "block")
