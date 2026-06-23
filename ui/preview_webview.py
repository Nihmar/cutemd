"""QWebEngineView-based preview widget for Markdown content.

After the first full-page load (with CSS + MathJax scripts), subsequent
updates only replace the <body> content via JavaScript, keeping MathJax
loaded and avoiding full-page reloads.  Large HTML documents (>2 MB)
are written to a temp file.
"""

from __future__ import annotations

import atexit
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

# ---------------------------------------------------------------------------
# Temp file for large HTML
# ---------------------------------------------------------------------------
_TEMP_DIR: Path | None = None


def _get_temp_dir() -> Path:
    global _TEMP_DIR
    if _TEMP_DIR is None:
        _TEMP_DIR = Path(tempfile.mkdtemp(prefix="cutemd_preview_"))
        atexit.register(_cleanup_temp_dir)
    return _TEMP_DIR


def _cleanup_temp_dir() -> None:
    import shutil

    if _TEMP_DIR and _TEMP_DIR.exists():
        shutil.rmtree(_TEMP_DIR, ignore_errors=True)


_HTML_SIZE_THRESHOLD = 2_000_000  # 2 MB


class _PreviewPage(QWebEnginePage):
    link_clicked = Signal(str)

    def acceptNavigationRequest(
        self,
        url: QUrl,
        nav_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            self.link_clicked.emit(url.toString())
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class PreviewWebView(QWebEngineView):
    """WebEngine-based Markdown preview with MathJax rendering."""

    link_clicked = Signal(str)
    scroll_ratio_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        page = _PreviewPage(self)
        self.setPage(page)
        page.link_clicked.connect(self.link_clicked.emit)

        settings = page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFixedFontSize, 13)

        self._base_dir: Path | None = None
        self._content_hash: int = 0
        self._pending_scroll_anchor: str = ""
        self._first_load_done = False

        page.scrollPositionChanged.connect(self._on_scroll_position_changed)
        self._scroll_ratio: float = 0.0
        self._syncing_scroll = False

        self.loadFinished.connect(self._on_load_finished)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_base_dir(self, d: Path) -> None:
        self._base_dir = d.resolve()

    def set_content(self, html: str, anchor: str = "") -> None:
        """Full page load (CSS + MathJax + body).  Use on first render."""
        content_hash = hash(html)
        if content_hash == self._content_hash and not anchor:
            return
        self._content_hash = content_hash
        self._pending_scroll_anchor = anchor
        self._first_load_done = True

        if len(html) < _HTML_SIZE_THRESHOLD:
            base_url = (
                QUrl.fromLocalFile(str(self._base_dir) + "/")
                if self._base_dir
                else QUrl()
            )
            self.setHtml(html, base_url)
        else:
            self._load_large_html(html, anchor)

    def set_body_html(
        self,
        body_html: str,
        theme_class: str,
        font_style: str,
        anchor: str = "",
    ) -> None:
        """Incremental update: replaces <body> inner HTML via JavaScript.

        Keeps MathJax loaded (no CDN re-fetch).  Call this AFTER the first
        set_content() has completed.
        """
        content_hash = hash(body_html)
        if content_hash == self._content_hash and not anchor:
            return
        self._content_hash = content_hash
        self._pending_scroll_anchor = anchor

        # JSON-encode the body HTML for safe injection into JavaScript
        body_json = json.dumps(body_html)

        anchor_json = json.dumps(anchor)

        js = (
            f"document.body.className = '{theme_class}';"
            f"document.body.style.cssText = '{font_style}';"
            f"document.body.innerHTML = {body_json};"
            # Re-typeset math with MathJax
            "if(window.MathJax && MathJax.typesetPromise) {"
            "  MathJax.typesetPromise().then(function() {"
            # After typesetting, scroll to anchor
            f"    var a = {anchor_json};"
            "    if(a) {"
            "      var el = document.querySelector('a[name=' + a + ']');"
            "      if(el) el.scrollIntoView({behavior:'instant', block:'start'});"
            "    }"
            "  });"
            "} else {"
            # No MathJax: scroll immediately
            f"  var a = {anchor_json};"
            "  if(a) {"
            "    var el = document.querySelector('a[name=' + a + ']');"
            "    if(el) el.scrollIntoView({behavior:'instant', block:'start'});"
            "  }"
            "}"
        )
        self.page().runJavaScript(js)

    def _load_large_html(self, html: str, anchor: str) -> None:
        base = self._base_dir if self._base_dir else _get_temp_dir()
        temp_file = base / ".cutemd_preview.html"
        temp_file.write_text(html, encoding="utf-8")
        self.setUrl(QUrl.fromLocalFile(str(temp_file)))

    def scroll_to_anchor(self, anchor: str) -> None:
        self._pending_scroll_anchor = anchor
        self.page().runJavaScript(
            f"""(function() {{
                var el = document.querySelector('a[name="{anchor}"]');
                if (el) el.scrollIntoView({{behavior:'instant',block:'start'}});
            }})();"""
        )

    def scroll_ratio(self) -> float:
        return self._scroll_ratio

    def set_scroll_ratio(self, ratio: float) -> None:
        self._syncing_scroll = True
        self.page().runJavaScript(
            f"window.scrollTo({{top:{ratio}*(document.body.scrollHeight-window.innerHeight),behavior:'instant'}});"
        )
        self._syncing_scroll = False

    @property
    def is_syncing_scroll(self) -> bool:
        return self._syncing_scroll

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_load_finished(self, ok: bool) -> None:
        if not ok or not self._pending_scroll_anchor:
            return
        self.scroll_to_anchor(self._pending_scroll_anchor)

    def _on_scroll_position_changed(self, pos: QPointF) -> None:
        if self._syncing_scroll:
            return
        self.page().runJavaScript(
            "document.body.scrollHeight - window.innerHeight",
            lambda max_h: self._compute_and_emit_ratio(pos.y(), max_h),
        )

    def _compute_and_emit_ratio(self, scroll_y: float, max_h) -> None:
        if isinstance(max_h, (int, float)) and max_h > 0:
            self._scroll_ratio = max(0.0, min(1.0, scroll_y / max_h))
        else:
            self._scroll_ratio = 0.0
        self.scroll_ratio_changed.emit(self._scroll_ratio)
