"""Worker thread for asynchronous preview rendering."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.preview_worker")


def _get_md():
    """Lazily build a MarkdownIt parser in the worker thread."""
    from markdown_it import MarkdownIt
    from mdit_py_plugins.dollarmath import dollarmath_plugin
    from markdown.math_renderers import (
        render_math_block, render_math_block_label,
        render_math_inline, render_math_inline_double,
    )
    from markdown.tools import highlight_code

    md = (
        MarkdownIt("commonmark", {"highlight": highlight_code})
        .enable(["table", "strikethrough"])
        .use(dollarmath_plugin)
    )
    md.renderer.rules["math_inline"] = render_math_inline
    md.renderer.rules["math_inline_double"] = render_math_inline_double
    md.renderer.rules["math_block"] = render_math_block
    md.renderer.rules["math_block_label"] = render_math_block_label
    return md


class PreviewWorker(QObject):
    result_ready = Signal(str)
    render_requested = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._md = None
        self.render_requested.connect(self._do_render)

    def _do_render(self, params: dict) -> None:
        import traceback

        text = params.get("text", "")
        _LOG.debug("_do_render: text_bytes=%d", len(text))

        try:
            if self._md is None:
                self._md = _get_md()

            from markdown.html_builder import build_html

            render_params = dict(params)
            render_params["md"] = self._md
            html = build_html(**render_params)
            if not isinstance(html, str):
                html = str(html)
        except Exception:
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
                "<body><pre>Render error:\n"
                + traceback.format_exc()
                + "</pre></body></html>"
            )

        _LOG.debug("_do_render: emitting html_len=%d preview=%s", len(html), html[:80])
        self.result_ready.emit(html)
