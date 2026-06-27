"""Async document renderer — runs Office/CBZ/EPUB rendering in a QThread.

Used by EditorTab._load_document() to avoid blocking the UI when
opening heavy document formats.
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.doc_renderer")


class AsyncDocRenderer(QThread):
    """Renders a document to HTML in a background thread."""

    result = Signal(str)  # html

    def __init__(self, path: Path, css: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._css = css

    def run(self) -> None:
        from markdown.document_renderers import (
            cbz_to_html,
            docx_to_html,
            epub_to_html,
            pptx_to_html,
            xlsx_to_html,
        )

        ext = self._path.suffix.lower()
        try:
            if ext == ".xlsx":
                html = xlsx_to_html(self._path, self._css)
            elif ext == ".docx":
                html = docx_to_html(self._path, self._css)
            elif ext == ".pptx":
                html = pptx_to_html(self._path, self._css)
            elif ext == ".cbz":
                html = cbz_to_html(self._path, self._css)
            elif ext == ".epub":
                html = epub_to_html(self._path, self._css)
            else:
                html = f"<p>[Unsupported format: {ext}]</p>"
        except Exception as exc:
            _LOG.debug("render error: %s", exc)
            html = f"<p>[Error rendering document: {exc}]</p>"

        self.result.emit(html)
