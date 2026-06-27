"""Worker thread for asynchronous preview rendering."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.preview_worker")

# Pre-built MarkdownIt parser — created once in the worker thread.
# We can't pass the main-thread parser through a queued signal
# because it doesn't survive cross-thread marshaling.
_MD: object = None


def _get_md():
    global _MD
    if _MD is None:
        from markdown_it import MarkdownIt
        from mdit_py_plugins.dollarmath import dollarmath_plugin
        from markdown.math_renderers import (
            render_math_block,
            render_math_block_label,
            render_math_inline,
            render_math_inline_double,
        )
        from markdown.tools import highlight_code

        _MD = (
            MarkdownIt("commonmark", {"highlight": highlight_code})
            .enable(["table", "strikethrough"])
            .use(dollarmath_plugin)
        )
        _MD.renderer.rules["math_inline"] = render_math_inline
        _MD.renderer.rules["math_inline_double"] = render_math_inline_double
        _MD.renderer.rules["math_block"] = render_math_block
        _MD.renderer.rules["math_block_label"] = render_math_block_label
    return _MD


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
        _LOG.debug("_do_render: text_bytes=%d", len(text))

        # Build params with a local MarkdownIt (can't pass across threads).
        render_params = dict(params)
        render_params["md"] = _get_md()

        try:
            html = build_html(**render_params)
        except BaseException as exc:
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "</head><body><pre>Preview rendering error: "
                + str(exc).replace("&", "&amp;").replace("<", "&lt;")
                + "</pre></body></html>"
            )

        _LOG.debug("_do_render: emitting html_len=%d", len(html) if html else 0)
        self.result_ready.emit(html)
