"""Worker thread for asynchronous preview rendering."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal


class PreviewWorker(QObject):
    """Runs ``build_html`` in a background thread so the editor stays
    responsive while images are resolved and dimensions are loaded.

    Use :attr:`render_requested` to start rendering and connect
    :attr:`result_ready` to receive the generated HTML.
    """

    result_ready = Signal(str)
    render_requested = Signal(object)  # actually carries a dict of kwargs

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.render_requested.connect(self._do_render)

    def _do_render(self, params: dict) -> None:
        from markdown.html_builder import build_html

        try:
            html = build_html(**params)
        except Exception:
            html = "<pre>Preview rendering error</pre>"
        self.result_ready.emit(html)
