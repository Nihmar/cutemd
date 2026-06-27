"""Link detection, hover highlights, broken-link markers, and preview popup.

Extracted from EditorTab to keep the tab class focused on file I/O
and editor/preview layout.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from core.logging import setup_logging

if TYPE_CHECKING:
    from ui.editor_tab import EditorTab
    from ui.link_preview_popup import LinkPreviewPopup

_LOG = setup_logging("cutemd.link_manager")

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")


class LinkManager:
    """Handles all link-related interactions in the editor viewport.

    - Detects Markdown / wikilink ranges under the mouse cursor
    - Manages hover underline and broken-link red underline
    - Controls the LinkPreviewPopup (show/hide on hover)
    """

    def __init__(self, tab: EditorTab) -> None:
        self._tab = tab
        self._editor = tab.editor
        self._viewport = tab.editor.viewport()

        self._broken_link_selections: list[QTextEdit.ExtraSelection] = []
        self._hover_link_key: tuple[int, int, int] | None = None
        self._hovered_link_target: str | None = None
        self._hover_cursor_pos: QPoint | None = None
        self._link_resolve_cache: dict[tuple[str, bool], Path | None] = {}

        # Popup timer (400 ms hover delay)
        self._link_preview_show_timer = QTimer(tab)
        self._link_preview_show_timer.setSingleShot(True)
        self._link_preview_show_timer.setInterval(400)
        self._link_preview_show_timer.timeout.connect(self._on_link_preview_show)

        # Cursor-tracking timer for popup dismiss
        self._popup_cursor_timer = QTimer(tab)
        self._popup_cursor_timer.setInterval(100)
        self._popup_cursor_timer.timeout.connect(self._check_popup_cursor)

        # Debounce timer for broken-link highlights (500 ms after last change).
        self._broken_link_timer = QTimer(tab)
        self._broken_link_timer.setSingleShot(True)
        self._broken_link_timer.setInterval(500)
        self._broken_link_timer.timeout.connect(self._do_refresh_broken)

    # ------------------------------------------------------------------
    # Popup access
    # ------------------------------------------------------------------

    @property
    def popup(self) -> LinkPreviewPopup:
        return self._tab._link_preview_popup

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def on_mouse_move(self, pos_in_block: int, block_text: str, block_number: int) -> bool:
        """Process a mouse-move event over the editor. Returns True if over a link."""
        link = self._link_range_at(pos_in_block, block_text)

        if link:
            target, display, start, end = link
            new_key = (block_number, start, end)
            if new_key != self._hover_link_key:
                self._hover_link_key = new_key

                block_start = self._editor.document().findBlockByNumber(block_number).position()
                sel = QTextCursor(self._editor.document())
                sel.setPosition(block_start + start)
                sel.setPosition(block_start + end, QTextCursor.MoveMode.KeepAnchor)

                fmt = QTextCharFormat()
                fmt.setFontUnderline(True)
                fmt.setUnderlineColor(QColor("#61afef"))
                extra = QTextEdit.ExtraSelection()
                extra.format = fmt
                extra.cursor = sel
                self._editor.setExtraSelections([extra])
                self._viewport.setCursor(Qt.CursorShape.PointingHandCursor)

            if target != self._hovered_link_target:
                self._hovered_link_target = target
                from PySide6.QtGui import QCursor
                self._hover_cursor_pos = QCursor.pos()
                self._link_preview_show_timer.start()
            return True
        else:
            if self._hover_link_key is not None:
                self._hover_link_key = None
                self._editor.setExtraSelections([])
                self._viewport.setCursor(Qt.CursorShape.IBeamCursor)
            if self._hovered_link_target is not None:
                self._hovered_link_target = None
                self._hover_cursor_pos = None
                self._link_preview_show_timer.stop()
                self.popup.hide_popup()
            return False

    def on_mouse_click(self, pos_in_block: int, block_text: str) -> tuple[str, str] | None:
        """Handle a mouse click on a link. Returns (target, display) or None."""
        link = self._link_range_at(pos_in_block, block_text)
        if link:
            self.popup.hide()
            self._hovered_link_target = None
            self._link_preview_show_timer.stop()
            return (link[0], link[1])
        self.popup.hide()
        self._hovered_link_target = None
        self._link_preview_show_timer.stop()
        return None

    def schedule_broken_refresh(self) -> None:
        """Schedule a broken-link highlight refresh after a debounce delay."""
        self._broken_link_timer.start()

    def _do_refresh_broken(self) -> None:
        """Actually perform the broken-link scan (called by debounce timer)."""
        text = self._tab._cached_text
        if not text:
            return
        self.refresh_broken_links(text)

    def refresh_broken_links(self, text: str) -> None:
        """Mark unresolved links in red using extra selections."""
        import time as _time
        t0 = _time.monotonic()

        from core.constants import BROKEN_LINK_LINE_LIMIT

        lines = text.count("\n") + 1
        if lines > BROKEN_LINK_LINE_LIMIT:
            self._broken_link_selections = []
            self._tab._apply_all_selections()
            return

        fmt = QTextCharFormat()
        fmt.setUnderlineColor(QColor("#e06c75"))
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)

        broken: list[QTextEdit.ExtraSelection] = []
        for pattern, target_group in ((_LINK_RE, 2), (_WIKILINK_RE, 1)):
            for m in pattern.finditer(text):
                target = m.group(target_group)
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                if self._resolve_link_target(target, quick=True) is not None:
                    continue
                sel = QTextEdit.ExtraSelection()
                sel.cursor = self._editor.textCursor()
                sel.cursor.setPosition(m.start())
                sel.cursor.setPosition(m.end(), QTextCursor.MoveMode.KeepAnchor)
                sel.format = fmt
                broken.append(sel)

        self._broken_link_selections = broken
        self._tab._apply_all_selections()

    # ------------------------------------------------------------------
    # Link preview popup
    # ------------------------------------------------------------------

    def _on_link_preview_show(self) -> None:
        target = self._hovered_link_target
        if target is None:
            return

        path = self._resolve_link_target(target)
        if path is None:
            return

        gap = 6
        popup_h = 380
        if self._hover_cursor_pos is not None:
            cx, cy = self._hover_cursor_pos.x(), self._hover_cursor_pos.y()
        else:
            from PySide6.QtGui import QCursor
            c = QCursor.pos()
            cx, cy = c.x(), c.y()
        x = cx
        y = cy - popup_h - gap
        if y < 0:
            y = cy + gap
        global_pos = QPoint(x, y)

        editor_font = self._editor.font()
        self.popup.show_for_path(path, global_pos, editor_font)
        self._popup_cursor_timer.start()

    def _check_popup_cursor(self) -> None:
        if not self.popup.isVisible():
            self._popup_cursor_timer.stop()
            return
        from PySide6.QtGui import QCursor
        vp = self._editor.viewport()
        local_pos = vp.mapFromGlobal(QCursor.pos())
        if not vp.rect().contains(local_pos):
            return
        cursor = self._editor.cursorForPosition(local_pos)
        block = cursor.block()
        pos = cursor.positionInBlock()
        link = self._link_range_at(pos, block.text())
        if link is None:
            self.popup.hide()
            self._popup_cursor_timer.stop()
            self._hovered_link_target = None
            self._hover_cursor_pos = None
            self._editor.setExtraSelections([])
            self._viewport.setCursor(Qt.CursorShape.IBeamCursor)

    # ------------------------------------------------------------------
    # Link resolution
    # ------------------------------------------------------------------

    def _resolve_link_target(self, target: str, quick: bool = False) -> Path | None:
        key = (target, quick)
        cached = self._link_resolve_cache.get(key)
        if cached is not None or key in self._link_resolve_cache:
            return cached
        source_dir = self._tab._file_path.parent if self._tab._file_path else Path.cwd()
        from core.link_resolution import resolve_link_target
        result = resolve_link_target(
            target, source_dir, self._tab._attachments_dir, quick=quick,
        )
        self._link_resolve_cache[key] = result
        return result

    def invalidate_cache(self) -> None:
        self._link_resolve_cache.clear()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @classmethod
    def link_range_at(
        cls, pos_in_block: int, text: str
    ) -> tuple[str, str, int, int] | None:
        for m in _WIKILINK_RE.finditer(text):
            if m.start() <= pos_in_block < m.end():
                inner = m.group(1).strip()
                if "|" in inner:
                    display, _, target = inner.partition("|")
                    return (target.strip(), display.strip(), m.start(), m.end())
                return (inner, inner, m.start(), m.end())
        for m in _LINK_RE.finditer(text):
            if m.start() <= pos_in_block < m.end():
                return (m.group(2).strip(), m.group(1).strip(), m.start(), m.end())
        return None

    @classmethod
    def _link_range_at(
        cls, pos_in_block: int, text: str
    ) -> tuple[str, str, int, int] | None:
        return cls.link_range_at(pos_in_block, text)
