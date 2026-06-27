"""Worker thread for asynchronous preview rendering."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.preview_worker")


class PreviewWorker(QObject):
    """Runs ``build_html`` and ``build_line_anchor_map`` in a background
    thread so the editor stays responsive.
    """

    result_ready = Signal(str, object)  # html, anchor_map
    render_requested = Signal(object)  # carries a dict of kwargs

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.render_requested.connect(self._do_render)

    def _do_render(self, params: dict) -> None:
        import sys
        from markdown.html_builder import build_html
        from core.link_resolution import build_line_anchor_map

        text = params.get("text", "")
        _LOG.debug("_do_render: text_bytes=%d", len(text))

        try:
            html = build_html(**params)
        except Exception as exc:
            _LOG.debug("_do_render: build_html FAILED — %s", exc)
            html = f"<pre>Preview rendering error: {exc}</pre>"

        _LOG.debug("_do_render: html_len=%d", len(html))

        try:
            anchor_map = build_line_anchor_map(params["md"], text)
        except Exception as exc:
            _LOG.debug("_do_render: anchor_map FAILED — %s", exc)
            anchor_map = []

        _LOG.debug("_do_render: emitting result_ready html=%d map=%d", len(html), len(anchor_map) if isinstance(anchor_map, list) else -1)
        self.result_ready.emit(html, anchor_map)
