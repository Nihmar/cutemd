"""Worker thread for asynchronous preview rendering.

Extracted from EditorTab to keep the tab class focused.
Computes both the HTML and the line→anchor map in the
background thread so the UI stays responsive.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.logging import setup_logging


class PreviewWorker(QObject):
    """Runs ``build_html`` and ``build_line_anchor_map`` in a background
    thread so the editor stays responsive.

    Use :attr:`render_requested` to start rendering and connect
    :attr:`result_ready` to receive the generated HTML and anchor map.
    """

    result_ready = Signal(str, object)  # html, anchor_map
    render_requested = Signal(object)  # actually carries a dict of kwargs

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.render_requested.connect(self._do_render)

    def _do_render(self, params: dict) -> None:
        _LOG = setup_logging("cutemd.preview_worker")
        _LOG.debug("_do_render: text_bytes=%d", len(params.get("text", "")))
        from markdown.html_builder import build_html
        from core.link_resolution import build_line_anchor_map

        try:
            html = build_html(**params)
        except Exception:
            html = self.tr("<pre>{}</pre>").format(
                self.tr("Preview rendering error")
            )

        # Compute the anchor map in the worker thread too.
        try:
            anchor_map = build_line_anchor_map(params["md"], params["text"])
        except Exception:
            anchor_map = []

        self.result_ready.emit(html, anchor_map)
