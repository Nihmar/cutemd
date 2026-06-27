"""Worker thread for asynchronous preview rendering."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.preview_worker")


class PreviewWorker(QObject):
    """Runs ``build_html`` in a background thread so the editor stays
    responsive while images are resolved and dimensions are loaded.
    """

    result_ready = Signal(str)  # html
    render_requested = Signal(object)  # carries a dict of kwargs

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.render_requested.connect(self._do_render)

    def _do_render(self, params: dict) -> None:
        from markdown.html_builder import build_html

        text = params.get("text", "")
        if not text.strip():
            return  # skip empty text — nothing to render

        _LOG.debug("_do_render: text_bytes=%d", len(text))
        html = ""

        try:
            html = build_html(**params)
        except BaseException as exc:
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "</head><body><pre>Preview rendering error</pre></body></html>"
            )

        if html:
            self.result_ready.emit(html)
