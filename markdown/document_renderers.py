"""Convert office documents and comic archives to HTML for in-app preview."""

from __future__ import annotations

import zipfile
from pathlib import Path
from html import escape


def _wrap_html(body: str, css: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body class="preview">{body}</body></html>"""


# ---------------------------------------------------------------------------
# XLSX  ->  HTML <table>
# ---------------------------------------------------------------------------

_XLSX_TABLE_CSS = """
.xlsx-toc { margin: 0.5em 0; line-height: 1.8; }
.xlsx-toc a { color: #61afef; text-decoration: none; margin-right: 1em; }
.xlsx-table { border-collapse: collapse; width: 100%; margin: 0.5em 0; font-size: 11px; }
.xlsx-table th, .xlsx-table td { border: 1px solid #777; padding: 3px 6px; text-align: left; white-space: nowrap; }
.xlsx-table th { font-weight: bold; background: #3c3c3c; }
.xlsx-table tr:nth-child(even) td { background: #2a2a2a; }
"""

def xlsx_to_html(path: Path, css: str, sheet_names: list[str] | None = None) -> str:
    """Convert an XLSX workbook to HTML table(s).

    Args:
        path: Path to the .xlsx file.
        css: Base CSS to include (appended with table-specific CSS).
        sheet_names: If not None, render only these sheets in order.
                     If None, render all sheets with a clickable TOC.
    """
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    names = sheet_names if sheet_names is not None else wb.sheetnames
    parts: list[str] = []

    # TOC when rendering all sheets
    if len(names) > 1 and sheet_names is None:
        toc_items = "".join(
            f'<a href="#sheet_{i}">{escape(n)}</a>'
            for i, n in enumerate(names)
        )
        parts.append(f'<div class="xlsx-toc">{toc_items}</div>')

    for idx, sheet_name in enumerate(names):
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        parts.append(f'<a name="sheet_{idx}"><h2>{escape(sheet_name)}</h2></a>')
        rows: list[str] = []
        for i, row in enumerate(ws.iter_rows(values_only=True, max_row=200)):
            tag = "th" if i == 0 else "td"
            cells = "".join(
                f"<{tag}>{escape(str(c)) if c is not None else ''}</{tag}>"
                for c in row
            )
            rows.append(f"<tr>{cells}</tr>")
        parts.append(f'<table class="xlsx-table">{"".join(rows)}</table>')

    wb.close()
    return _wrap_html("\n".join(parts), css + _XLSX_TABLE_CSS)


# ---------------------------------------------------------------------------
# DOCX  ->  HTML (headings, paragraphs, tables)
# ---------------------------------------------------------------------------

def docx_to_html(path: Path, css: str) -> str:
    """Convert a DOCX document to HTML paragraphs."""
    from docx import Document

    doc = Document(str(path))
    parts: list[str] = []

    for el in doc.element.body:
        tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
        if tag == 'p':
            text = _docx_paragraph_text(el)
            if not text:
                continue
            p_style = el.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr')
            style_val = None
            if p_style is not None:
                p_style_el = p_style.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pStyle')
                if p_style_el is not None:
                    style_val = p_style_el.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val')

            if style_val and style_val.startswith('Heading'):
                level = style_val.replace('Heading', '')
                if level.isdigit() and 1 <= int(level) <= 6:
                    parts.append(f'<h{level}>{escape(text)}</h{level}>')
                    continue
            parts.append(f'<p>{escape(text)}</p>')
        elif tag == 'tbl':
            parts.append(_docx_table_to_html(el))

    return _wrap_html('\n'.join(parts), css)


def _docx_paragraph_text(p_el) -> str:
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    texts = []
    for r in p_el.iter(f'{ns}r'):
        t_el = r.find(f'{ns}t')
        if t_el is not None and t_el.text:
            texts.append(t_el.text)
    return ''.join(texts).strip()


def _docx_table_to_html(tbl_el) -> str:
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    rows_html = []
    for row_el in tbl_el.iter(f'{ns}tr'):
        cells = []
        for cell_el in row_el.iter(f'{ns}tc'):
            text = ''
            for p in cell_el.iter(f'{ns}p'):
                t = _docx_paragraph_text(p)
                if t:
                    text += t + ' '
            cells.append(f'<td>{escape(text.strip())}</td>')
        rows_html.append('<tr>' + ''.join(cells) + '</tr>')
    return '<table>' + '\n'.join(rows_html) + '</table>'


# ---------------------------------------------------------------------------
# PPTX  ->  HTML (slides with text)
# ---------------------------------------------------------------------------

def pptx_to_html(path: Path, css: str) -> str:
    """Convert a PPTX presentation to HTML -- text from each slide."""
    from pptx import Presentation

    prs = Presentation(str(path))
    parts: list[str] = []
    for i, slide in enumerate(prs.slides):
        parts.append(f'<h3>Slide {i + 1}</h3>')
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        parts.append(f'<p>{escape(text)}</p>')
        parts.append('<hr>')
    return _wrap_html('\n'.join(parts), css)


# ---------------------------------------------------------------------------
# CBZ  ->  HTML (image gallery)
# ---------------------------------------------------------------------------

def cbz_to_html(path: Path, css: str) -> str:
    """Convert a CBZ (comic book zip) to HTML showing all images."""
    _IMG_EXTS = frozenset(
        {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp"}
    )
    images: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                ext = Path(name).suffix.lower()
                if ext in _IMG_EXTS:
                    data = zf.read(name)
                    import base64
                    mime = "image/png" if ext == ".png" else "image/jpeg"
                    if ext in (".jpg", ".jpeg"):
                        mime = "image/jpeg"
                    elif ext == ".gif":
                        mime = "image/gif"
                    elif ext == ".svg":
                        mime = "image/svg+xml"
                    elif ext == ".webp":
                        mime = "image/webp"
                    b64 = base64.b64encode(data).decode("ascii")
                    images.append(f'<p><img src="data:{mime};base64,{b64}" /></p>')
    except (zipfile.BadZipFile, FileNotFoundError):
        return _wrap_html("<p>[Cannot read: file is corrupted]</p>", css)
    except Exception:
        pass

    body = "\n".join(images) if images else "<p>[No images found in CBZ file]</p>"
    style = css + """
    .cbz-gallery img {
        max-width: 100%; height: auto; display: block; margin: 1em auto;
    }"""
    return _wrap_html(f'<div class="cbz-gallery">{body}</div>', style)


# ---------------------------------------------------------------------------
# EPUB  ->  HTML (chapter text)
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Remove HTML/XML tags, returning clean text."""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def epub_to_html(path: Path, css: str) -> str:
    """Convert an EPUB to HTML -- text from each chapter."""
    parts: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist()):
                ext = Path(name).suffix.lower()
                if ext not in (".xhtml", ".html", ".htm", ".xml"):
                    continue
                content = zf.read(name).decode("utf-8", errors="replace")
                if ext == ".xml" and "<html" not in content.lower()[:500]:
                    continue
                text = _strip_html(content)
                if not text:
                    continue
                title = Path(name).stem
                parts.append(f"<h2>{escape(title)}</h2>")
                for para in text.split("\n\n"):
                    para = para.strip()
                    if para:
                        parts.append(f"<p>{escape(para)}</p>")
    except (zipfile.BadZipFile, FileNotFoundError):
        return _wrap_html("<p>[Cannot read: file is corrupted]</p>", css)
    except Exception:
        pass

    body = "\n".join(parts[:50]) if parts else "<p>[No content found in EPUB]</p>"
    return _wrap_html(body, css)
