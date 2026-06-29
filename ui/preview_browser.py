"""QWebEngineView replacement for the preview pane.

Provides:
- PreviewWebEnginePage  — custom QWebEnginePage with link/wikilink interception
- PreviewWebEngineView  — QWebEngineView with the same public API as
  the old PreviewTextBrowser so that EditorTab needs minimal changes
- get_image_size()     — QImage-based size provider (unchanged, used by html_builder)
"""

from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QImage,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from core.logging import setup_logging

_LOG = setup_logging("cutemd.preview_browser")


# ---------------------------------------------------------------------------
# Image size provider (unchanged — used by markdown/html_builder.py)
# ---------------------------------------------------------------------------

def _fit_image(img: QImage, max_width: int) -> QImage:
    if img.width() <= max_width:
        return img
    return img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)


def get_image_size(path_str: str, max_width: int) -> tuple[int, int] | None:
    """QImage-based size provider for markdown.image_utils.add_img_dimensions."""
    try:
        img = QImage(path_str)
    except Exception:
        return None
    if img.isNull():
        return None
    img = _fit_image(img, max_width)
    return (img.width(), img.height())


# ---------------------------------------------------------------------------
# Custom QWebEnginePage — navigation interception
# ---------------------------------------------------------------------------

class PreviewWebEnginePage(QWebEnginePage):
    """Custom QWebEnginePage that intercepts link/wikilink navigation.

    - ``http://cutemd-copy/`` URLs → decode and copy to clipboard
    - External http/https → open in system browser
    - Local file:// or plain paths → emit ``file_link_clicked``
    - ``cutemd-scroll://`` → emit ``preview_scrolled`` (preview→editor sync)
    - Everything else → blocked (return False)
    """
    file_link_clicked = Signal(str)
    preview_scrolled = Signal(str)  # anchor name e.g. "b5"

    def __init__(self, parent=None):
        super().__init__(parent)
        _LOG.debug("DIAG PreviewWebEnginePage.__init__ id=%s", id(self))

    def acceptNavigationRequest(
        self, url: QUrl, nav_type, is_main_frame: bool
    ) -> bool:
        url_str = url.toString()
        _LOG.debug("DIAG acceptNavigationRequest: id=%s url=%s nav_type=%s is_main=%s",
                   id(self), url_str[:120], nav_type, is_main_frame)

        # Allow the initial page load (NavigationTypeTyped from setContent).
        # Blocking it causes loadFinished(ok=False) and a blank page.
        from PySide6.QtWebEngineCore import QWebEnginePage
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeTyped:
            _LOG.debug("DIAG acceptNavigationRequest: allowing typed navigation")
            return True

        # Preview scroll sync — user scrolled the preview via mouse/touch
        if url_str.startswith("https://cutemd-scroll/"):
            anchor = url_str.removeprefix("https://cutemd-scroll/")
            # Dedup: Chromium may call acceptNavigationRequest multiple times
            # for the same navigation (main frame + sub-resource checks).
            last_anchor = getattr(self, '_last_scroll_anchor', '')
            if anchor != last_anchor:
                self._last_scroll_anchor = anchor
                self.preview_scrolled.emit(anchor)
            return False

        # Copy-code interception
        if url_str.startswith("http://cutemd-copy/"):
            payload = url_str.removeprefix("http://cutemd-copy/")
            _LOG.debug("cutemd-copy payload length: %d", len(payload))
            try:
                decoded = base64.urlsafe_b64decode(payload).decode("utf-8")
                _LOG.debug("decoded %d chars to clipboard", len(decoded))
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(decoded)
                    _LOG.debug("clipboard.setText succeeded")
                else:
                    _LOG.debug("clipboard is None")
            except Exception as exc:
                _LOG.debug("cutemd-copy error: %s", exc)
            return False

        # External URLs → system browser
        if url_str.startswith(("http://", "https://", "www.")):
            QDesktopServices.openUrl(url)
            return False

        # Local file/image paths
        target = url.toLocalFile() if url.isLocalFile() else url_str
        if target:
            self.file_link_clicked.emit(target)
        return False  # Block all navigation


# ---------------------------------------------------------------------------
# Custom QWebEngineView — drop-in replacement for PreviewTextBrowser
# ---------------------------------------------------------------------------

class PreviewWebEngineView(QWebEngineView):
    """QWebEngineView with the same public API as the old QTextBrowser preview.

    Signals:
        file_link_clicked(str) — a local file path was clicked.
    """
    file_link_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Prevent the preview from stealing focus from the editor on reload.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._page = PreviewWebEnginePage(self)
        _LOG.debug("DIAG PreviewWebEngineView.__init__ setting page id=%s", id(self._page))
        self.setPage(self._page)
        # Verify the page was actually set
        _LOG.debug("DIAG after setPage: page id=%s page_class=%s",
                   id(self.page()), type(self.page()).__name__)
        self._page.file_link_clicked.connect(self.file_link_clicked)

        self._base_dir: Path | None = None
        self._attachments_dir: Path | None = None
        # JS injected flag — set True after each page load
        self._js_injected = False

        # Connect preview_scrolled for preview→editor sync
        self._page.preview_scrolled.connect(self._on_preview_user_scrolled)
        self._scroll_anchor_callback = None  # set by EditorTab

        # Allow loading file:// images from local content
        settings = self.page().settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )

        # Diagnostic: log when page finishes loading
        self.loadFinished.connect(self._on_load_finished)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _on_load_finished(self, ok: bool) -> None:
        _LOG.debug("DIAG loadFinished: ok=%s", ok)

    # ------------------------------------------------------------------
    # Public API — compatible with the old PreviewTextBrowser
    # ------------------------------------------------------------------

    def set_base_dir(self, d: Path) -> None:
        resolved = d.resolve()
        if self._base_dir != resolved:
            self._base_dir = resolved

    def set_attachments_dir(self, d: Path | None) -> None:
        resolved = d.resolve() if d is not None else None
        self._attachments_dir = resolved

    def setReadOnly(self, _read_only: bool) -> None:
        """No-op — kept for API compatibility with QTextBrowser."""
        pass

    def setOpenLinks(self, _open: bool) -> None:
        """No-op — navigation is handled by acceptNavigationRequest."""
        pass

    def setOpenExternalLinks(self, _open: bool) -> None:
        """No-op — external links are handled by acceptNavigationRequest."""
        pass

    def viewport(self):
        """Return a widget suitable for installing event filters.

        QWebEngineView is itself the visible widget, unlike QAbstractScrollArea
        which has a separate viewport().
        """
        return self

    def setPlainText(self, text: str) -> None:
        """Display plain text (used for "Rendering…" placeholder)."""
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        html = f"<!DOCTYPE html><html><body style='padding:16px'>{escaped}</body></html>"
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".html")
        with open(fd, "w", encoding="utf-8") as f:
            f.write(html)
        self.page().load(QUrl.fromLocalFile(tmp_path))

    def setHtml(self, html: str) -> None:
        """Load HTML content.

        Writes to a temp file and loads via file:// URL to avoid the
        size limits of both QWebEngineView.setHtml() (2 MB) and
        page().setContent() / data: URLs (~2-3 MB).
        """
        import tempfile

        # Inject <base> tag so relative links (wikilinks) resolve to the
        # vault directory, not the temp file's directory.
        base_tag = ""
        if self._base_dir is not None:
            base_url = QUrl.fromLocalFile(str(self._base_dir) + "/")
            base_tag = f'<base href="{base_url.toString()}">'

        # Insert <base> after <head> if present, otherwise at start.
        head_pos = html.find("<head>")
        if head_pos >= 0:
            html = html[:head_pos + 6] + base_tag + html[head_pos + 6:]
        else:
            html = base_tag + html

        fd, tmp_path = tempfile.mkstemp(suffix=".html")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(html)
            _LOG.debug("DIAG setHtml: len=%d written to %s base_tag=%s page_id=%s",
                       len(html), tmp_path, bool(base_tag), id(self.page()))
            self.page().load(QUrl.fromLocalFile(tmp_path))
            self._js_injected = False  # re-inject after load
        except Exception as exc:
            _LOG.debug("DIAG setHtml: tempfile error: %s", exc)
            import traceback
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Preview → Editor scroll sync (JS scroll listener)
    # ------------------------------------------------------------------

    _SCROLL_LISTENER_JS = (
        "(function(){"
        "if(window._cutemd_scroll_listener){return;}"
        "window._cutemd_scroll_listener=true;"
        "window._cutemd_syncing=false;"
        "window.addEventListener('scroll',function(){"
        "if(window._cutemd_syncing)return;"
        "var anchors=document.querySelectorAll('a[name]');"
        "var best=null;"
        "anchors.forEach(function(a){"
        "var r=a.getBoundingClientRect();"
        "if(r.top<=5)best=a.getAttribute('name');"
        "});"
        "if(best)window.location='https://cutemd-scroll/'+best;"
        "},{passive:true});"
        "})();"
    )

    def _inject_scroll_listener(self) -> None:
        """Inject the JS scroll listener after page load."""
        if self._js_injected:
            return
        self._js_injected = True
        self.page().runJavaScript(self._SCROLL_LISTENER_JS)

    def _on_preview_user_scrolled(self, anchor: str) -> None:
        """Forward the anchor from the JS scroll listener to EditorTab."""
        if self._scroll_anchor_callback:
            self._scroll_anchor_callback(anchor)

    def set_scroll_syncing(self, syncing: bool) -> None:
        """Tell the JS that we're about to programmatically scroll the
        preview (True), or that we're done (False). While True, the JS
        scroll listener ignores scroll events."""
        val = "true" if syncing else "false"
        self.page().runJavaScript(f"window._cutemd_syncing={val};")

    # ------------------------------------------------------------------
    # Context menu — block Chromium defaults
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        """Suppress the Chromium default context menu.
        The preview is read-only, so there is nothing useful to offer.
        """
        event.ignore()
