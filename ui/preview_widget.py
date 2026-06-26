"""Abstract base class for Markdown preview widgets."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class PreviewWidget(QWidget):
    """Base interface for Markdown preview implementations.

    Concrete implementations must override all public methods.
    ``TextBrowserPreview`` is the default (QTextBrowser-based).
    """

    file_link_clicked = Signal(str)
    scroll_changed = Signal(int)

    def set_read_only(self, v: bool) -> None:
        raise NotImplementedError

    def set_open_links(self, v: bool) -> None:
        raise NotImplementedError

    def set_open_external_links(self, v: bool) -> None:
        raise NotImplementedError

    def set_base_dir(self, d: Path) -> None:
        raise NotImplementedError

    def set_attachments_dir(self, d: Path | None) -> None:
        raise NotImplementedError

    def set_html(self, html: str) -> None:
        raise NotImplementedError

    def set_plain_text(self, text: str) -> None:
        raise NotImplementedError

    def scroll_to_anchor(self, anchor: str) -> None:
        raise NotImplementedError

    def content_width(self) -> int:
        raise NotImplementedError

    def anchor_at_viewport_top(self) -> str | None:
        """Return the anchor name (e.g. ``'b3'``) visible at the top of the viewport, or ``None``."""
        raise NotImplementedError

    def scroll_position(self) -> int:
        raise NotImplementedError

    def max_scroll(self) -> int:
        raise NotImplementedError
