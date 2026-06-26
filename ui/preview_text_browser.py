"""QTextBrowser-based implementation of PreviewWidget."""

import base64
import logging
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QImage, QDesktopServices, QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QTextBrowser, QVBoxLayout

from markdown.image_utils import needs_loading, resolve_image_path
from ui.preview_widget import PreviewWidget

_LOG = logging.getLogger("cutemd.preview_text_browser")


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


class _InnerBrowser(QTextBrowser):
    """QTextBrowser subclass that loads local images via loadResource()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self._base_dir: Path | None = None
        self._attachments_dir: Path | None = None

    def set_base_dir(self, d: Path) -> None:
        resolved = d.resolve()
        if self._base_dir != resolved:
            self._base_dir = resolved

    def set_attachments_dir(self, d: Path | None) -> None:
        self._attachments_dir = d.resolve() if d is not None else None

    def loadResource(self, resource_type: int, url: QUrl):
        if resource_type == int(QTextDocument.ImageResource):
            url_str = url.toLocalFile() if url.isLocalFile() else url.toString()
            if self._base_dir is not None and needs_loading(url_str):
                resolved = resolve_image_path(url_str, self._base_dir, self._attachments_dir)
                if resolved is not None:
                    try:
                        img = QImage(str(resolved))
                    except Exception:
                        img = QImage()
                    if not img.isNull():
                        return img
        return super().loadResource(resource_type, url)


class TextBrowserPreview(PreviewWidget):
    """QTextBrowser-based Markdown preview widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._browser = _InnerBrowser()
        self._browser.anchorClicked.connect(self._on_anchor_clicked)
        self._browser.verticalScrollBar().valueChanged.connect(self.scroll_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._browser)

    # -- PreviewWidget interface --------------------------------------------

    def set_read_only(self, v: bool) -> None:
        self._browser.setReadOnly(v)

    def set_open_links(self, v: bool) -> None:
        self._browser.setOpenLinks(v)

    def set_open_external_links(self, v: bool) -> None:
        self._browser.setOpenExternalLinks(v)

    def set_base_dir(self, d: Path) -> None:
        self._browser.set_base_dir(d)

    def set_attachments_dir(self, d: Path | None) -> None:
        self._browser.set_attachments_dir(d)

    def set_html(self, html: str) -> None:
        self._browser.setHtml(html)

    def set_plain_text(self, text: str) -> None:
        self._browser.setPlainText(text)

    def content_width(self) -> int:
        return self._browser.width()

    def scroll_to_anchor(self, anchor: str) -> None:
        self._browser.scrollToAnchor(anchor)

    def anchor_at_viewport_top(self) -> str | None:
        cursor = self._browser.cursorForPosition(QPoint(0, 0))
        block = cursor.block()
        doc = self._browser.document()
        for _ in range(5):
            if not block.isValid():
                break
            names = block.charFormat().anchorNames()
            for name in names:
                if name.startswith("b"):
                    return name
            block_pos = block.position()
            for offset in range(10):
                check_pos = block_pos + offset
                if check_pos >= doc.characterCount():
                    break
                temp = QTextCursor(doc)
                temp.setPosition(check_pos)
                for name in temp.charFormat().anchorNames():
                    if name.startswith("b"):
                        return name
            block = block.previous()
        return None

    def scroll_position(self) -> int:
        return self._browser.verticalScrollBar().value()

    def max_scroll(self) -> int:
        return self._browser.verticalScrollBar().maximum()

    def set_scroll_position(self, value: int) -> None:
        self._browser.verticalScrollBar().setValue(value)

    def content_height(self) -> int:
        return self._browser.document().size().height()

    def get_anchor_positions(self) -> dict[str, int]:
        """Return {anchor_name: y_pixel} for every <a name="bN"> in the document."""
        doc = self._browser.document()
        positions: dict[str, int] = {}
        block = doc.firstBlock()
        while block.isValid():
            # Check block-level anchor names (headings, etc.)
            for name in block.charFormat().anchorNames():
                if name.startswith("b"):
                    positions[name] = int(block.layout().position().y())
            # Check character-level anchors (paragraphs, fences, etc.)
            block_pos = block.position()
            block_len = block.length()
            for offset in range(block_len):
                pos = block_pos + offset
                if pos >= doc.characterCount():
                    break
                cursor = QTextCursor(doc)
                cursor.setPosition(pos)
                for name in cursor.charFormat().anchorNames():
                    if name.startswith("b") and name not in positions:
                        positions[name] = int(block.layout().position().y())
            block = block.next()
        return positions

    # -- Internal link routing ----------------------------------------------

    def _on_anchor_clicked(self, url: QUrl) -> None:
        url_str = url.toString()
        _LOG.debug("_on_anchor_clicked: %s", url_str[:120])

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
            return
        if url_str.startswith(("http://", "https://", "www.")):
            QDesktopServices.openUrl(url)
            return
        target = url.toLocalFile() if url.isLocalFile() else url_str
        if target:
            self.file_link_clicked.emit(target)

    # -- QWidget overrides -------------------------------------------------

    def viewport(self):
        return self._browser.viewport()

    @property
    def _max_width(self) -> int:
        return max(self.content_width(), 200)
