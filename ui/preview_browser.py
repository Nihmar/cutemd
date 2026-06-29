"""QWebEngineView replacement for the preview pane.

Provides:
- PreviewWebEnginePage  — custom QWebEnginePage with link/wikilink interception
- PreviewWebEngineView  — QWebEngineView with the same public API as
  the old PreviewTextBrowser so that EditorTab needs minimal changes
- get_image_size()     — QImage-based size provider (unchanged, used by html_builder)
"""

from __future__ import annotations

import base64
import os
import tempfile
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
    - ``cutemd-toggle://`` URLs → emit ``checkbox_toggled`` signal
    - In-page fragment links (``#id``) → scroll to element
    - External http/https → open in system browser
    - Local file:// or plain paths → emit ``file_link_clicked``
    - Everything else → blocked (return False)
    """

    file_link_clicked = Signal(str)
    checkbox_toggled = Signal(str)  # "LINE|STATE" — e.g. "42|checked" or "42|unchecked"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_dir: str = ""
        _LOG.debug("DIAG PreviewWebEnginePage.__init__ id=%s", id(self))

    def javaScriptConsoleMessage(self, level, message, line, source):
        if "cutemd:" in message:
            _LOG.debug("JS: %s", message)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        url_str = url.toString()
        _LOG.debug(
            "DIAG acceptNavigationRequest: id=%s url=%s nav_type=%s is_main=%s",
            id(self),
            url_str[:120],
            nav_type,
            is_main_frame,
        )

        # Allow the initial page load (NavigationTypeTyped from setContent).
        # Blocking it causes loadFinished(ok=False) and a blank page.
        from PySide6.QtWebEngineCore import QWebEnginePage

        if nav_type == QWebEnginePage.NavigationType.NavigationTypeTyped:
            _LOG.debug("DIAG acceptNavigationRequest: allowing typed navigation")
            return True

        # Handle in-page fragment links (TOC, footnotes, etc.)
        if url.hasFragment() and url.path() in ("", "/", self._base_dir):
            fragment = url.fragment()
            if fragment:
                self.runJavaScript(
                    f'var el=document.getElementById("{fragment}");'
                    f'if(el)el.scrollIntoView({{block:"start",behavior:"instant"}});'
                )
            return False

        # Checkbox toggle interception
        if url_str.startswith("http://cutemd-toggle/"):
            parts = url_str.removeprefix("http://cutemd-toggle/").split("/")
            if len(parts) == 2:
                payload = f"{parts[0]}|{parts[1]}"
                _LOG.debug("cutemd-toggle payload: %s", payload)
                self.checkbox_toggled.emit(payload)
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
        checkbox_toggled(str)  — "LINE|STATE" for task list toggle.
    """

    file_link_clicked = Signal(str)
    checkbox_toggled = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Prevent the preview from stealing focus from the editor on reload.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._page = PreviewWebEnginePage(self)
        _LOG.debug(
            "DIAG PreviewWebEngineView.__init__ setting page id=%s", id(self._page)
        )
        self.setPage(self._page)
        # Verify the page was actually set
        _LOG.debug(
            "DIAG after setPage: page id=%s page_class=%s",
            id(self.page()),
            type(self.page()).__name__,
        )
        self._page.file_link_clicked.connect(self.file_link_clicked)
        self._page.checkbox_toggled.connect(self.checkbox_toggled)

        self._base_dir: Path | None = None
        self._attachments_dir: Path | None = None
        # JS injected flag — set True after each page load
        self._js_injected = False
        # Reusable temp file — avoids disk allocation on every preview refresh.
        self._tmp_path: str | None = None

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
            self._page._base_dir = str(resolved)

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
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = (
            f"<!DOCTYPE html><html><body style='padding:16px'>{escaped}</body></html>"
        )
        fd, tmp_path = tempfile.mkstemp(suffix=".html")
        with open(fd, "w", encoding="utf-8") as f:
            f.write(html)
        self.page().load(QUrl.fromLocalFile(tmp_path))

    def setHtml(self, html: str) -> None:
        """Load HTML content.

        Uses a reusable temp file + load() to avoid the implicit size
        limits of setHtml() and setContent() (~2 MB).  The file is
        overwritten in-place — no allocation per refresh.
        """
        # Inject <base> tag so relative links (wikilinks) resolve to the
        # vault directory.
        base_tag = ""
        if self._base_dir is not None:
            base_url = QUrl.fromLocalFile(str(self._base_dir) + "/")
            base_tag = f'<base href="{base_url.toString()}">'

        head_pos = html.find("<head>")
        if head_pos >= 0:
            html = html[: head_pos + 6] + base_tag + html[head_pos + 6 :]
        else:
            html = base_tag + html

        # Reuse or create a single temp file.
        if self._tmp_path is None:
            fd, self._tmp_path = tempfile.mkstemp(suffix=".html")
            os.close(fd)
        with open(self._tmp_path, "w", encoding="utf-8") as f:
            f.write(html)

        self._js_injected = False
        self.page().load(QUrl.fromLocalFile(self._tmp_path))

    # ------------------------------------------------------------------
    # Preview → Editor scroll sync (JS scroll listener)
    # ------------------------------------------------------------------

    _SCROLL_LISTENER_JS = (
        "(function(){"
        "if(window._cutemd_listener)return;"
        "window._cutemd_listener=1;"
        "window._cutemd_line='';"
        "window._cutemd_at_bottom=false;"
        "if(typeof window._cutemd_suppress==='undefined')window._cutemd_suppress=0;"
        "var _last_reported='';"
        "window.addEventListener('scroll',function(){"
        "var now=Date.now();"
        "var sy=window.scrollY,sh=document.body.scrollHeight;"
        "if(window._cutemd_suppress&&now<window._cutemd_suppress){"
        "console.log('cutemd: scroll suppressed sy='+sy+' sh='+sh);"
        "return;"
        "}"
        "var a=document.querySelectorAll('a[data-line]');"
        "var best='';"
        "for(var i=a.length-1;i>=0;i--){"
        "if(a[i].getBoundingClientRect().top<=5){"
        "best=a[i].getAttribute('data-line');break;"
        "}"
        "}"
        "if(best!=='')window._cutemd_line=best;"
        "if(best!==_last_reported){"
        "console.log('cutemd: scroll SET line='+best+' was='+_last_reported+' sy='+sy+' sh='+sh);"
        "_last_reported=best;"
        "}"
        "window._cutemd_at_bottom="
        "(window.innerHeight+Math.ceil(window.scrollY)>=document.body.scrollHeight-2);"
        "},{passive:true});"
        "})();"
    )

    _CHECKBOX_JS = (
        "(function(){"
        "if(window._cutemd_checkboxes)return;"
        "window._cutemd_checkboxes=1;"
        "var _last_toggle=0;"
        "document.addEventListener('click',function(e){"
        "var cb=e.target;"
        "if(!cb.classList||!cb.classList.contains('task-list-item-checkbox'))return;"
        "var now=Date.now();"
        "if(now-_last_toggle<80)return;"
        "_last_toggle=now;"
        "console.log('cutemd: checkbox click, checked='+cb.checked);"
        "var li=cb.closest('li');"
        "if(!li)return;"
        "e.stopPropagation();"
        "var anchor=li.querySelector('a[data-line]');"
        "if(!anchor){"
        "var prev=li.previousElementSibling;"
        "while(prev){"
        "anchor=prev.querySelector('a[data-line]');"
        "if(!anchor)anchor=prev.matches('a[data-line]')?prev:null;"
        "if(anchor)break;"
        "prev=prev.previousElementSibling;"
        "}"
        "}"
        "var line=anchor?anchor.getAttribute('data-line'):'0';"
        "var state=cb.checked?'checked':'unchecked';"
        "console.log('cutemd: toggle line='+line+' state='+state);"
        "var a=document.createElement('a');"
        "a.href='http://cutemd-toggle/'+line+'/'+state;"
        "a.style.display='none';"
        "document.body.appendChild(a);"
        "a.click();"
        "document.body.removeChild(a);"
        "},{capture:true});"
        "})();"
    )

    _KATEX_JS = (
        "(function(){"
        "if(window._cutemd_katex)return;"
        "window._cutemd_katex=1;"
        "if(!window.katex)return;"
        "try{"
        "var all=document.querySelectorAll('.math-katex[data-latex]');"
        "var vh=window.innerHeight;"
        "var rendered=new Set();"
        "all.forEach(function(el){"
        "var r=el.getBoundingClientRect();"
        "if(r.top<vh+200&&r.bottom>-200){"
        "var latex=el.getAttribute('data-latex');"
        "if(!latex)return;"
        "var display=el.classList.contains('math-block');"
        "try{katex.render(latex,el,{displayMode:display,throwOnError:false});rendered.add(el);"
        "}catch(e){console.warn('kaTeX error:',e);}"
        "}"
        "});"
        "console.log('cutemd: katex visible init '+rendered.size+'/'+all.length);"
        "var observer=new IntersectionObserver(function(entries){"
        "if(!entries.length)return;"
        "var batch=[];"
        "entries.forEach(function(entry){"
        "if(!entry.isIntersecting)return;"
        "var el=entry.target;"
        "if(rendered.has(el))return;"
        "batch.push(el);"
        "observer.unobserve(el);"
        "});"
        "if(!batch.length)return;"
        "var i=0;"
        "function renderNext(){"
        "if(i>=batch.length)return;"
        "var el=batch[i++];"
        "var latex=el.getAttribute('data-latex');"
        "if(!latex){renderNext();return;}"
        "var display=el.classList.contains('math-block');"
        "try{katex.render(latex,el,{displayMode:display,throwOnError:false});rendered.add(el);"
        "}catch(e){console.warn('kaTeX error:',e);}"
        "if(i<batch.length)requestAnimationFrame(renderNext);"
        "}"
        "requestAnimationFrame(renderNext);"
        "},{rootMargin:'50px'});"
        "all.forEach(function(el){if(!rendered.has(el))observer.observe(el);});"
        "}catch(e){console.warn('kaTeX init error:',e);}"
        "})();"
    )

    def _inject_scroll_listener(self) -> None:
        """Inject the JS scroll listener, checkbox handler, and KaTeX after page load."""
        if self._js_injected:
            return
        self._js_injected = True
        # Set suppress BEFORE any JS runs so scroll events from the
        # initial KaTeX render don't pollute _cutemd_line.
        self.page().runJavaScript("window._cutemd_suppress=Date.now()+2000;")
        self.page().runJavaScript(self._SCROLL_LISTENER_JS)
        self.page().runJavaScript(self._CHECKBOX_JS)
        self.page().runJavaScript(self._KATEX_JS)

    # ------------------------------------------------------------------
    # Context menu — block Chromium defaults
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        """Suppress the Chromium default context menu.
        The preview is read-only, so there is nothing useful to offer.
        """
        event.ignore()
