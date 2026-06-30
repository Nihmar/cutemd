"""Async document renderer — runs Office/CBZ/EPUB/CSV rendering in a QThread.

Used by EditorTab._load_document() to avoid blocking the UI when
opening heavy document formats.
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.doc_renderer")


class AsyncDocRenderer(QThread):
    """Renders a document to HTML in a background thread.

    For XLSX/DOCX/PPTX/CBZ/EPUB, uses the full document_renderers.
    For CSV/TSV, produces a monospace <pre> table (matching the
    floating link-preview popup style).
    """

    result = Signal(str)  # html

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self) -> None:
        ext = self._path.suffix.lower()
        try:
            if ext == ".xlsx":
                html = _render_xlsx(self._path)
            elif ext == ".docx":
                html = _render_docx(self._path)
            elif ext == ".pptx":
                html = _render_pptx(self._path)
            elif ext == ".cbz":
                html = _render_cbz(self._path)
            elif ext == ".epub":
                html = _render_epub(self._path)
            elif ext in (".csv", ".tsv"):
                html = _render_csv(self._path)
            else:
                html = f"<p>[Unsupported format: {ext}]</p>"
        except Exception as exc:
            _LOG.debug("render error: %s", exc)
            html = f"<p>[Error rendering document: {exc}]</p>"

        self.result.emit(html)


# ---------------------------------------------------------------------------
# Internal render helpers (imported lazily in run())
# ---------------------------------------------------------------------------


def _render_xlsx(path: Path) -> str:
    from md_parser.document_renderers import xlsx_to_html
    # Use empty CSS so table styling comes only from _XLSX_TABLE_CSS
    return xlsx_to_html(path, "")


def _render_docx(path: Path) -> str:
    from md_parser.document_renderers import docx_to_html
    return docx_to_html(path, "")


def _render_pptx(path: Path) -> str:
    from md_parser.document_renderers import pptx_to_html
    return pptx_to_html(path, "")


def _render_cbz(path: Path) -> str:
    from md_parser.document_renderers import cbz_to_html
    return cbz_to_html(path, "")


def _render_epub(path: Path) -> str:
    from md_parser.document_renderers import epub_to_html
    return epub_to_html(path, "")


def _render_csv(path: Path) -> str:
    import csv

    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)[:100]

    if not rows:
        return ""

    col_widths = [0] * max(len(r) for r in rows)
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    lines = [
        " \u2502 ".join(c.ljust(col_widths[i]) for i, c in enumerate(row))
        for row in rows
    ]
    body = "\n".join(lines)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        "body { font-family: monospace; font-size: 12px; "
        "white-space: pre; margin: 8px; }"
        "</style></head><body>" + body + "</body></html>"
    )
