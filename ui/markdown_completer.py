"""Smart editing helpers for the Markdown editor.

- Auto-pair delimiters: ``*`` → ``**``, ``_`` → ``_|_``, ``~`` → ``~~``, `` ` `` → `` `|` ``
- Auto-pair brackets: ``[`` → ``[]()``, ``(`` → ``()``
- List / blockquote continuation on Enter
- Backspace removes empty delimiter pairs
- Tag autocomplete: Ctrl+Space after ``#`` shows known vault tags

All features are togglable via settings.
"""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
)

from core.logging import setup_logging
from ui.widgets import CuteListWidget

_LOG = setup_logging("cutemd.completer")

# ---------------------------------------------------------------------------
# Default settings (used when no QSettings value exists)
# ---------------------------------------------------------------------------

DEFAULT_SMART_EDITING = {
    "enabled": True,
    "auto_pair": True,
    "auto_pair_brackets": True,
    "continue_lists": True,
    "backspace_pairs": True,
    "link_style": "md",
}

# ---------------------------------------------------------------------------
# Regex patterns for list / blockquote detection
# ---------------------------------------------------------------------------

_RE_UNORDERED = re.compile(r"^(\s*)([-*+])\s+(.*)")
_RE_ORDERED = re.compile(r"^(\s*)(\d+)\.\s+(.*)")
_RE_TASK = re.compile(r"^(\s*)([-*+])\s+\[([ xX])\]\s+(.*)")
_RE_BLOCKQUOTE = re.compile(r"^(\s*)(>\s*)(.*)")
_RE_LIST_MARKER = re.compile(r"^(\s*)([-*+]|\d+\.)\s+")

# Delimiters that are auto-doubled (cursor placed AFTER the pair)
_PAIR_AFTER = {"*"}
# Delimiters that are auto-paired singly (cursor placed BETWEEN)
_PAIR_BETWEEN = {"_", "~", "`"}


class MarkdownAutoCompleter(QObject):
    """Installs as an event filter on a :class:`QPlainTextEdit` and
    intercepts key presses to provide smart Markdown completions."""

    def __init__(
        self,
        editor: QPlainTextEdit,
        settings: dict[str, Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._editor = editor
        self._cfg: dict[str, Any] = dict(DEFAULT_SMART_EDITING)
        if settings:
            self._cfg.update(settings)
        editor.installEventFilter(self)

        # Tag autocomplete state
        self._tag_list: list[str] = []
        self._tag_popup: QFrame | None = None
        self._tag_filter: QLineEdit | None = None
        self._tag_list_widget: CuteListWidget | None = None

        # File autocomplete state
        self._file_list: list[str] = []
        self._file_popup: QFrame | None = None
        self._file_filter: QLineEdit | None = None
        self._file_list_widget: CuteListWidget | None = None

        # HTML tag autocomplete state
        self._html_popup: QFrame | None = None
        self._html_filter: QLineEdit | None = None
        self._html_list_widget: CuteListWidget | None = None

    # ------------------------------------------------------------------
    # HTML tag list
    # ------------------------------------------------------------------
    _HTML_TAGS: list[str] = [
        "a", "abbr", "article", "aside", "b", "blockquote", "br", "button",
        "caption", "cite", "code", "col", "colgroup", "dd", "del",
        "details", "dfn", "div", "dl", "dt", "em", "fieldset", "figcaption",
        "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
        "head", "header", "hr", "html", "i", "iframe", "img", "input",
        "ins", "kbd", "label", "legend", "li", "link", "main", "mark",
        "meta", "nav", "ol", "option", "p", "picture", "pre", "section",
        "select", "small", "span", "strong", "sub", "summary", "sup",
        "table", "tbody", "td", "textarea", "tfoot", "th", "thead",
        "time", "tr", "u", "ul", "video",
    ]
    _VOID_TAGS: set[str] = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_settings(self, settings: dict[str, Any]) -> None:
        self._cfg.update(settings)

    def set_tag_list(self, tags: list[str]) -> None:
        """Update the tag list used for Ctrl+Space autocomplete."""
        self._tag_list = sorted(set(tags))

    def set_file_list(self, files: list[str]) -> None:
        """Update the file list (relative paths) used for link autocomplete."""
        self._file_list = sorted(set(files))

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._editor and event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event  # type: ignore[assignment]
            if (key_event.key() == Qt.Key.Key_Space
                    and key_event.modifiers() == Qt.KeyboardModifier.ControlModifier):
                _LOG.debug("eventFilter: Ctrl+Space detected")
                # Check context: tag (after #) takes priority over file link
                if self._after_hash():
                    return self._show_tag_completer()
                if self._inside_file_link():
                    return self._show_file_completer()
                if self._inside_frontmatter_tags():
                    _LOG.debug("eventFilter: inside frontmatter tags, showing tag completer")
                    return self._show_tag_completer()
                if self._after_html_tag():
                    return self._show_html_tag_completer()
                # Fallback: if there's a # before cursor, try tags
                return self._show_tag_completer()
            return self._handle_key(key_event)

        # Popup keyboard handling
        if obj is self._tag_list_widget and event.type() == QEvent.Type.KeyPress:
            return self._handle_tag_popup_key(event)
        if obj is self._tag_filter and event.type() == QEvent.Type.KeyPress:
            return self._handle_tag_filter_key(event)
        if obj is self._file_list_widget and event.type() == QEvent.Type.KeyPress:
            return self._handle_file_popup_key(event)
        if obj is self._file_filter and event.type() == QEvent.Type.KeyPress:
            return self._handle_file_filter_key(event)

        if obj is self._html_list_widget and event.type() == QEvent.Type.KeyPress:
            return self._handle_html_popup_key(event)
        if obj is self._html_filter and event.type() == QEvent.Type.KeyPress:
            return self._handle_html_filter_key(event)

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Key dispatch
    # ------------------------------------------------------------------

    def _handle_key(self, event: QKeyEvent) -> bool:
        if not self._cfg.get("enabled", True):
            return False

        key = event.key()
        modifiers = event.modifiers()

        # Only act on plain key presses (no Ctrl / Alt / Meta)
        allowed = Qt.KeyboardModifier.NoModifier | Qt.KeyboardModifier.ShiftModifier
        if modifiers & ~allowed:
            return False

        text = event.text()

        # --- Enter: continue lists / blockquotes ---
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._cfg.get("continue_lists", True):
            return self._continue_list()

        # --- Backspace: remove empty pairs ---
        if key == Qt.Key.Key_Backspace and self._cfg.get("backspace_pairs", True):
            return self._handle_backspace()

        # --- Auto-close HTML tags on > ---
        if text == ">" and self._cfg.get("auto_pair", True):
            return self._auto_close_html_tag()

        # --- Auto-pair brackets ---
        if text in ("[", "(") and self._cfg.get("auto_pair_brackets", True):
            return self._auto_bracket(text)

        # --- Auto-pair Markdown delimiters ---
        if self._cfg.get("auto_pair", True):
            if text in _PAIR_AFTER:
                return self._auto_pair_double(text)
            if text in _PAIR_BETWEEN:
                return self._auto_pair_single(text)

        return False

    # ------------------------------------------------------------------
    # Auto-pair: double delimiter (cursor AFTER pair, e.g. ``**``  for bold)
    # ------------------------------------------------------------------

    def _auto_pair_double(self, char: str) -> bool:
        cursor = self._editor.textCursor()

        if cursor.hasSelection():
            sel = cursor.selectedText()
            marker = char + char
            cursor.insertText(marker + sel + marker)
            return True

        cursor.insertText(char + char)
        self._editor.setTextCursor(cursor)
        return True

    # ------------------------------------------------------------------
    # Auto-pair: single delimiter (cursor BETWEEN pair, e.g. ``_|_``  for italic)
    # ------------------------------------------------------------------

    def _auto_pair_single(self, char: str) -> bool:
        cursor = self._editor.textCursor()

        if cursor.hasSelection():
            sel = cursor.selectedText()
            cursor.insertText(char + sel + char)
            # Place cursor after the closing delimiter
            return True

        # Skip if next character matches (useful for doubling: _ then _ → __)
        if self._next_char(cursor) == char:
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, 1)
            self._editor.setTextCursor(cursor)
            return True

        cursor.insertText(char + char)
        cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
        self._editor.setTextCursor(cursor)
        return True

    # ------------------------------------------------------------------
    # Auto-pair: brackets  [  (  ]
    # ------------------------------------------------------------------

    def _auto_bracket(self, open_char: str) -> bool:
        cursor = self._editor.textCursor()

        # --- [ on a list line → insert checkbox ---
        if open_char == "[" and self._at_list_marker(cursor):
            self._insert_checkbox(cursor)
            return True

        close_char = "]" if open_char == "[" else ")"
        link_style = self._cfg.get("link_style", "md")

        if cursor.hasSelection():
            sel = cursor.selectedText()
            if open_char == "[" and link_style == "wiki":
                cursor.insertText("[[" + sel + "]]")
            else:
                cursor.insertText(open_char + sel + close_char)
            return True

        if open_char == "[":
            if link_style == "wiki":
                # [[ → [[|]]  cursor between double brackets
                cursor.insertText("[[]]")
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 2)
            else:
                # [ → []()  cursor between brackets
                cursor.insertText("[]()")
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 3)
        else:
            # ( → ()  cursor between
            cursor.insertText("()")
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)

        self._editor.setTextCursor(cursor)
        return True

    # ------------------------------------------------------------------
    # List-marker detection  →  checkbox insertion
    # ------------------------------------------------------------------

    def _at_list_marker(self, cursor: QTextCursor) -> bool:
        """Return True if the cursor is inside the list-marker zone
        (indent + marker + space), meaning the user wants a checkbox."""
        text = cursor.block().text()
        pos = cursor.positionInBlock()
        m = _RE_LIST_MARKER.match(text)
        if m:
            return pos <= m.end()
        return False

    def _insert_checkbox(self, cursor: QTextCursor) -> None:
        cursor.insertText("[ ] ")
        self._editor.setTextCursor(cursor)

    # ------------------------------------------------------------------
    # List / blockquote continuation on Enter
    # ------------------------------------------------------------------

    def _continue_list(self) -> bool:
        cursor = self._editor.textCursor()
        text = cursor.block().text()

        # Task list
        m = _RE_TASK.match(text)
        if m:
            indent, marker, _checked, content = m.groups()
            if content.strip():
                cursor.insertText("\n" + indent + marker + " [ ] ")
                return True
            self._clear_block(cursor)
            return True

        # Ordered list
        m = _RE_ORDERED.match(text)
        if m:
            indent, num, content = m.groups()
            if content.strip():
                cursor.insertText("\n" + indent + str(int(num) + 1) + ". ")
                return True
            self._clear_block(cursor)
            return True

        # Unordered list
        m = _RE_UNORDERED.match(text)
        if m:
            indent, marker, content = m.groups()
            if content.strip():
                cursor.insertText("\n" + indent + marker + " ")
                return True
            self._clear_block(cursor)
            return True

        # Blockquote
        m = _RE_BLOCKQUOTE.match(text)
        if m:
            indent, prefix, content = m.groups()
            if content.strip():
                cursor.insertText("\n" + indent + prefix)
                return True
            self._clear_block(cursor)
            return True

        return False

    # ------------------------------------------------------------------
    # Backspace on empty pairs:  **|**  →  (empty)
    # ------------------------------------------------------------------

    def _handle_backspace(self) -> bool:
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            return False

        pos = cursor.position()
        full = self._editor.toPlainText()

        for pair_char in ("*", "_", "~", "`"):
            pair = pair_char + pair_char
            if pos >= 2 and pos + 2 <= len(full):
                if full[pos - 2 : pos] == pair and full[pos : pos + 2] == pair:
                    cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 2)
                    cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 4)
                    cursor.insertText("")
                    return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _next_char(self, cursor: QTextCursor) -> str:
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
        ch = cursor.selectedText()
        cursor.clearSelection()
        return ch

    @staticmethod
    def _clear_block(cursor: QTextCursor) -> None:
        """Select the current block and replace it with an empty string."""
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.MoveAnchor)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("")

    # ------------------------------------------------------------------
    # Context detection
    # ------------------------------------------------------------------

    def _after_hash(self) -> bool:
        """Check if there is a ``#`` before the cursor (for tag completion)."""
        cursor = self._editor.textCursor()
        pos_in_block = cursor.positionInBlock()
        block_text = cursor.block().text()
        for i in range(pos_in_block - 1, -1, -1):
            ch = block_text[i]
            if ch == "#":
                return True
            if ch.isspace():
                break
        return False

    def _inside_file_link(self) -> bool:
        """Check if the cursor is inside a markdown URL ``](...)`` or
        wikilink ``[[...]]``."""
        cursor = self._editor.textCursor()
        pos_in_block = cursor.positionInBlock()
        block_text = cursor.block().text()

        # Check for markdown link: inside ](...)
        md_start = block_text.rfind("](", 0, pos_in_block)
        if md_start >= 0:
            close = block_text.find(")", md_start)
            if close >= pos_in_block:
                return True

        # Check for wikilink: inside [[...]]
        wiki_start = block_text.rfind("[[", 0, pos_in_block)
        if wiki_start >= 0:
            close = block_text.find("]]", wiki_start + 2)
            if close >= pos_in_block:
                return True

        return False

    def _inside_frontmatter_tags(self) -> bool:
        """Check if cursor is in the frontmatter ``tags:`` line/block."""
        cursor = self._editor.textCursor()
        block_text = cursor.block().text().strip()
        block_num = cursor.block().blockNumber()

        _LOG.debug("_inside_frontmatter_tags: block_text=%r block_num=%d", block_text, block_num)

        if block_text.startswith("tags:"):
            _LOG.debug("_inside_frontmatter_tags: matched 'tags:'")
            return True
        if block_text.startswith("- ") or block_text.startswith("  - ") or block_text == "-":
            doc = self._editor.document()
            for n in range(block_num - 1, -1, -1):
                b = doc.findBlockByNumber(n).text().strip()
                _LOG.debug("_inside_frontmatter_tags: walk back n=%d b=%r", n, b)
                if b.startswith("tags:"):
                    return True
                if b == "---" or b == "..." or b.startswith("#"):
                    break
        return False

    def _after_html_tag(self) -> bool:
        """Check if cursor is after ``<`` and before ``>`` or end of word."""
        cursor = self._editor.textCursor()
        pos_in_block = cursor.positionInBlock()
        block_text = cursor.block().text()
        # Find the last < before cursor
        lt = block_text.rfind("<", 0, pos_in_block)
        if lt < 0:
            return False
        after_lt = block_text[lt:pos_in_block]
        # Must be at <tagname position: e.g. <d  or <div
        if not after_lt.startswith("<"):
            return False
        tag_part = after_lt[1:].strip()
        # No > between < and cursor
        if ">" in tag_part:
            return False
        return True

    # ------------------------------------------------------------------
    # HTML tag autocomplete
    # ------------------------------------------------------------------

    def _auto_close_html_tag(self) -> bool:
        """When the user types ``>``, auto-insert the closing tag if the
        opening tag looks like a known HTML element."""
        cursor = self._editor.textCursor()
        pos_in_block = cursor.positionInBlock()
        block_text = cursor.block().text()

        # The > was just typed, so cursor is AFTER it.  Find the preceding <
        gt_pos = pos_in_block - 1  # position of the just-typed >
        lt = block_text.rfind("<", 0, gt_pos)
        if lt < 0:
            return False
        tag_part = block_text[lt + 1:gt_pos].strip().lower()
        if not tag_part:
            return False
        # Only trigger for known HTML tags
        if tag_part not in self._HTML_TAGS and tag_part.split()[0] not in self._HTML_TAGS:
            return False

        base_tag = tag_part.split()[0]
        if base_tag in self._VOID_TAGS:
            return False

        closing = f"</{base_tag}>"
        cursor.insertText(closing)
        # Move cursor back between tags
        cursor.movePosition(QTextCursor.MoveOperation.Left,
                          QTextCursor.MoveMode.MoveAnchor, len(closing))
        self._editor.setTextCursor(cursor)
        return True

    # ------------------------------------------------------------------
    # HTML tag popup (Ctrl+Space after <)
    # ------------------------------------------------------------------

    def _show_html_tag_completer(self) -> bool:
        cursor = self._editor.textCursor()
        pos_in_block = cursor.positionInBlock()
        block_text = cursor.block().text()
        lt = block_text.rfind("<", 0, pos_in_block)
        partial = block_text[lt + 1:pos_in_block].strip().lower()

        self._html_partial = partial
        self._html_insert_pos = cursor.position()
        self._html_lt_pos = lt
        self._html_block = cursor.block()

        self._html_popup = _make_popup(self._editor.viewport())
        layout = self._html_popup.layout()

        self._html_filter = QLineEdit(self._html_popup)
        self._html_filter.setPlaceholderText(self._editor.tr("HTML tag\u2026"))
        self._html_filter.setText(partial)
        self._html_filter.selectAll()
        self._html_filter.textChanged.connect(self._on_html_filter_changed)
        self._html_filter.installEventFilter(self)
        layout.addWidget(self._html_filter)

        self._html_list_widget = CuteListWidget(self._html_popup)
        self._html_list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._html_list_widget.itemClicked.connect(self._on_html_tag_selected)
        self._html_list_widget.installEventFilter(self)
        layout.addWidget(self._html_list_widget)

        self._populate_html_list(partial)

        cursor_rect = self._editor.cursorRect(cursor)
        vp = self._editor.viewport()
        global_pos = vp.mapToGlobal(cursor_rect.bottomLeft())
        w = max(200, self._html_list_widget.sizeHintForColumn(0) + 20)
        h = 240
        self._html_popup.setGeometry(global_pos.x(), global_pos.y() + 2, w, h)
        self._html_popup.show()
        self._html_filter.setFocus()
        return True

    def _populate_html_list(self, filter_text: str) -> None:
        self._html_list_widget.clear()
        low = filter_text.strip().lower()
        tags = [t for t in self._HTML_TAGS if low in t] if low else list(self._HTML_TAGS)
        for tag in tags:
            self._html_list_widget.addItem(QListWidgetItem(tag))
        if self._html_list_widget.count() > 0:
            self._html_list_widget.setCurrentRow(0)

    def _on_html_filter_changed(self, text: str) -> None:
        self._populate_html_list(text)

    def _on_html_tag_selected(self, item: QListWidgetItem) -> None:
        tag = item.text()
        self._hide_html_popup()
        self._insert_html_tag(tag)

    def _hide_html_popup(self) -> None:
        if self._html_popup is not None:
            self._html_popup.hide()
            self._html_popup.deleteLater()
            self._html_popup = None
            self._html_filter = None
            self._html_list_widget = None

    def _insert_html_tag(self, tag: str) -> None:
        """Insert the HTML tag, replacing the partial text after <."""
        block = getattr(self, "_html_block", None)
        if block is None or not block.isValid():
            return
        lt_pos = getattr(self, "_html_lt_pos", 0)
        insert_pos = getattr(self, "_html_insert_pos", 0)

        # Remove the partial tag name
        cursor = self._editor.textCursor()
        block_start = block.position()
        cursor.setPosition(block_start + lt_pos + 1)  # after <
        cursor.setPosition(insert_pos, QTextCursor.MoveMode.KeepAnchor)
        if cursor.hasSelection():
            cursor.removeSelectedText()  # Don't kill the <

        if tag in self._VOID_TAGS:
            if tag == "img":
                cursor.insertText(tag + ' src="" />')
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 3)
            else:
                cursor.insertText(tag + " />")
        else:
            cursor.insertText(tag + "></" + tag + ">")
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, len(tag) + 3)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    # ------------------------------------------------------------------
    # Tag autocomplete
    # ------------------------------------------------------------------

    def _show_tag_completer(self) -> bool:
        """Show a popup list of matching tags below the cursor."""
        if not self._tag_list:
            _LOG.debug("_show_tag_completer: no tags in list")
            return False

        cursor = self._editor.textCursor()
        block_text = cursor.block().text()
        pos_in_block = cursor.positionInBlock()

        frontmatter_mode = self._inside_frontmatter_tags()
        if frontmatter_mode:
            # Extract partial: text after "- " or after "tags: "
            if block_text.strip().startswith("tags:"):
                partial = block_text[block_text.find("tags:") + 5:pos_in_block].strip().strip(",")
            else:
                dash = block_text.find("- ")
                if dash >= 0:
                    partial = block_text[dash + 2:pos_in_block].strip().strip(",")
                else:
                    partial = ""
            self._hash_pos = -1  # signal frontmatter mode
        else:
            hash_pos = -1
            for i in range(pos_in_block - 1, -1, -1):
                ch = block_text[i]
                if ch == "#":
                    hash_pos = i
                    break
                if ch.isspace():
                    break
            if hash_pos < 0:
                return False
            partial = block_text[hash_pos + 1:pos_in_block]
            self._hash_pos = hash_pos

        _LOG.debug("_show_tag_completer: partial=%r fm_mode=%s", partial, frontmatter_mode)

        self._pos_in_block = pos_in_block
        self._hash_block = cursor.block()
        self._frontmatter_mode = frontmatter_mode

        self._tag_popup = _make_popup(self._editor.viewport())
        layout = self._tag_popup.layout()

        self._tag_filter = QLineEdit(self._tag_popup)
        self._tag_filter.setPlaceholderText(self._editor.tr("Filter tags\u2026"))
        self._tag_filter.setText(partial)
        self._tag_filter.selectAll()
        self._tag_filter.textChanged.connect(self._on_tag_filter_changed)
        self._tag_filter.installEventFilter(self)
        layout.addWidget(self._tag_filter)

        self._tag_list_widget = CuteListWidget(self._tag_popup)
        self._tag_list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tag_list_widget.itemClicked.connect(self._on_tag_selected)
        self._tag_list_widget.installEventFilter(self)
        layout.addWidget(self._tag_list_widget)

        self._populate_tag_list(self._tag_list)
        if self._tag_filter.text():
            self._on_tag_filter_changed(self._tag_filter.text())

        cursor_rect = self._editor.cursorRect(cursor)
        vp = self._editor.viewport()
        global_pos = vp.mapToGlobal(cursor_rect.bottomLeft())
        w = max(200, self._tag_list_widget.sizeHintForColumn(0) + 20)
        h = 280
        self._tag_popup.setGeometry(global_pos.x(), global_pos.y() + 2, w, h)
        self._tag_popup.show()
        self._tag_filter.setFocus()
        return True

    def _populate_tag_list(self, tags: list[str]) -> None:
        self._tag_list_widget.clear()
        for tag in tags:
            self._tag_list_widget.addItem(QListWidgetItem(tag))
        if self._tag_list_widget.count() > 0:
            self._tag_list_widget.setCurrentRow(0)

    def _on_tag_filter_changed(self, text: str) -> None:
        low = text.strip().lower()
        matching = ([t for t in self._tag_list if low in t.lower()]
                    if low else list(self._tag_list))
        self._populate_tag_list(matching)

    def _on_tag_selected(self, item: QListWidgetItem) -> None:
        tag = item.text()
        self._hide_tag_popup()
        self._insert_tag_completion(tag)

    def _insert_tag_completion(self, tag: str) -> None:
        if not getattr(self, "_hash_block", None):
            return
        block = self._hash_block
        if not block.isValid():
            return
        cursor = self._editor.textCursor()

        if getattr(self, "_frontmatter_mode", False):
            # Frontmatter tags: insert without #
            block_start = block.position()
            cursor.setPosition(block_start + self._pos_in_block)
            cursor.insertText(tag)
        else:
            block_start = block.position()
            cursor.setPosition(block_start + self._hash_pos)
            cursor.setPosition(block_start + self._pos_in_block,
                              QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText("#" + tag)

        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _hide_tag_popup(self) -> None:
        if self._tag_popup is not None:
            self._tag_popup.hide()
            self._tag_popup.deleteLater()
            self._tag_popup = None
            self._tag_filter = None
            self._tag_list_widget = None

    def _handle_tag_popup_key(self, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._tag_list_widget.currentItem()
            if item:
                self._on_tag_selected(item)
            return True
        if event.key() == Qt.Key.Key_Escape:
            self._hide_tag_popup()
            self._editor.setFocus()
            return True
        if event.key() == Qt.Key.Key_Down:
            row = self._tag_list_widget.currentRow()
            if row < self._tag_list_widget.count() - 1:
                self._tag_list_widget.setCurrentRow(row + 1)
            return True
        if event.key() == Qt.Key.Key_Up:
            row = self._tag_list_widget.currentRow()
            if row > 0:
                self._tag_list_widget.setCurrentRow(row - 1)
            return True
        if event.key() == Qt.Key.Key_Home:
            if self._tag_list_widget.count() > 0:
                self._tag_list_widget.setCurrentRow(0)
            return True
        if event.key() == Qt.Key.Key_End:
            cnt = self._tag_list_widget.count()
            if cnt > 0:
                self._tag_list_widget.setCurrentRow(cnt - 1)
            return True
        if event.key() == Qt.Key.Key_PageUp:
            row = self._tag_list_widget.currentRow()
            page = max(5, self._tag_list_widget.height() // 22)
            self._tag_list_widget.setCurrentRow(max(0, row - page))
            return True
        if event.key() == Qt.Key.Key_PageDown:
            row = self._tag_list_widget.currentRow()
            page = max(5, self._tag_list_widget.height() // 22)
            cnt = self._tag_list_widget.count()
            self._tag_list_widget.setCurrentRow(min(cnt - 1, row + page))
            return True
        return False

    def _handle_tag_filter_key(self, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                           Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                           Qt.Key.Key_Home, Qt.Key.Key_End,
                           Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return self._handle_tag_popup_key(event)
        if event.key() == Qt.Key.Key_Escape:
            self._hide_tag_popup()
            self._editor.setFocus()
            return True
        return False

    # ------------------------------------------------------------------
    # File autocomplete (Ctrl+Space inside link brackets)
    # ------------------------------------------------------------------

    def _show_file_completer(self) -> bool:
        """Show a popup with filterable file list."""
        if not self._file_list:
            _LOG.debug("_show_file_completer: no files in list")
            return False

        cursor = self._editor.textCursor()
        block_text = cursor.block().text()
        pos_in_block = cursor.positionInBlock()

        # Determine link context
        self._link_context: str = ""  # 'md' or 'wiki'
        self._link_start: int = -1
        self._link_end: int = -1

        md_start = block_text.rfind("](", 0, pos_in_block)
        if md_start >= 0:
            close = block_text.find(")", md_start)
            if close >= pos_in_block:
                self._link_context = "md"
                self._link_start = md_start + 2  # after ](
                self._link_end = close

        if not self._link_context:
            wiki_start = block_text.rfind("[[", 0, pos_in_block)
            if wiki_start >= 0:
                close = block_text.find("]]", wiki_start + 2)
                if close >= pos_in_block:
                    self._link_context = "wiki"
                    self._link_start = wiki_start + 2
                    self._link_end = close

        if not self._link_context:
            return False

        partial = block_text[self._link_start:pos_in_block]
        matching = ([f for f in self._file_list if partial.lower() in f.lower()]
                    if partial else list(self._file_list))
        _LOG.debug("_show_file_completer: partial=%r %d matching",
                   partial, len(matching))
        if not matching:
            return False

        self._link_block = cursor.block()

        self._file_popup = _make_popup(self._editor.viewport())
        layout = self._file_popup.layout()

        self._file_filter = QLineEdit(self._file_popup)
        self._file_filter.setPlaceholderText(self._editor.tr("Filter files\u2026"))
        self._file_filter.setText(partial)
        self._file_filter.selectAll()
        self._file_filter.textChanged.connect(self._on_file_filter_changed)
        self._file_filter.installEventFilter(self)
        layout.addWidget(self._file_filter)

        self._file_list_widget = CuteListWidget(self._file_popup)
        self._file_list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._file_list_widget.itemClicked.connect(self._on_file_selected)
        self._file_list_widget.installEventFilter(self)
        self._populate_file_list(matching)
        layout.addWidget(self._file_list_widget)

        cursor_rect = self._editor.cursorRect(cursor)
        vp = self._editor.viewport()
        global_pos = vp.mapToGlobal(cursor_rect.bottomLeft())
        w = max(280, self._file_list_widget.sizeHintForColumn(0) + 20)
        h = 280
        self._file_popup.setGeometry(global_pos.x(), global_pos.y() + 2, w, h)
        self._file_popup.show()
        self._file_filter.setFocus()
        return True

    def _populate_file_list(self, files: list[str]) -> None:
        """Fill the file list widget with filtered files."""
        self._file_list_widget.clear()
        for f in files:
            self._file_list_widget.addItem(QListWidgetItem(f))
        if self._file_list_widget.count() > 0:
            self._file_list_widget.setCurrentRow(0)

    def _on_file_filter_changed(self, text: str) -> None:
        """Re-filter the file list based on filter text."""
        low = text.strip().lower()
        matching = [f for f in self._file_list if low in f.lower()] if low else list(self._file_list)
        self._populate_file_list(matching)

    def _on_file_selected(self, item: QListWidgetItem) -> None:
        path = item.text()
        self._hide_file_popup()
        self._insert_link_target(path)

    def _insert_link_target(self, target: str) -> None:
        """Replace the link content between delimiters with *target*."""
        if not getattr(self, "_link_block", None):
            return
        block = self._link_block
        if not block.isValid():
            return
        cursor = self._editor.textCursor()
        block_start = block.position()
        cursor.setPosition(block_start + self._link_start)
        cursor.setPosition(block_start + self._link_end,
                          QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(target)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _hide_file_popup(self) -> None:
        if self._file_popup is not None:
            self._file_popup.hide()
            self._file_popup.deleteLater()
            self._file_popup = None
            self._file_filter = None
            self._file_list_widget = None

    def _handle_file_popup_key(self, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._file_list_widget.currentItem()
            if item:
                self._on_file_selected(item)
            return True
        if event.key() == Qt.Key.Key_Escape:
            self._hide_file_popup()
            self._editor.setFocus()
            return True
        return False

    def _handle_file_popup_key(self, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._file_list_widget.currentItem()
            if item:
                self._on_file_selected(item)
            return True
        if event.key() == Qt.Key.Key_Escape:
            self._hide_file_popup()
            self._editor.setFocus()
            return True
        if event.key() == Qt.Key.Key_Down:
            row = self._file_list_widget.currentRow()
            if row < self._file_list_widget.count() - 1:
                self._file_list_widget.setCurrentRow(row + 1)
            return True
        if event.key() == Qt.Key.Key_Up:
            row = self._file_list_widget.currentRow()
            if row > 0:
                self._file_list_widget.setCurrentRow(row - 1)
            return True
        if event.key() == Qt.Key.Key_Home:
            if self._file_list_widget.count() > 0:
                self._file_list_widget.setCurrentRow(0)
            return True
        if event.key() == Qt.Key.Key_End:
            cnt = self._file_list_widget.count()
            if cnt > 0:
                self._file_list_widget.setCurrentRow(cnt - 1)
            return True
        if event.key() == Qt.Key.Key_PageUp:
            row = self._file_list_widget.currentRow()
            page = max(5, self._file_list_widget.height() // 22)
            self._file_list_widget.setCurrentRow(max(0, row - page))
            return True
        if event.key() == Qt.Key.Key_PageDown:
            row = self._file_list_widget.currentRow()
            page = max(5, self._file_list_widget.height() // 22)
            cnt = self._file_list_widget.count()
            self._file_list_widget.setCurrentRow(min(cnt - 1, row + page))
            return True
        return False

    def _handle_file_filter_key(self, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                           Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                           Qt.Key.Key_Home, Qt.Key.Key_End,
                           Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return self._handle_file_popup_key(event)
        if event.key() == Qt.Key.Key_Escape:
            self._hide_file_popup()
            self._editor.setFocus()
            return True
        return False

    def _handle_html_popup_key(self, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self._html_list_widget.currentItem()
            if item:
                self._on_html_tag_selected(item)
            return True
        if event.key() == Qt.Key.Key_Escape:
            self._hide_html_popup()
            self._editor.setFocus()
            return True
        return False

    def _handle_html_filter_key(self, event: QKeyEvent) -> bool:
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                           Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                           Qt.Key.Key_Home, Qt.Key.Key_End,
                           Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return self._handle_html_popup_key(event)
        if event.key() == Qt.Key.Key_Escape:
            self._hide_html_popup()
            self._editor.setFocus()
            return True
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_popup(parent: QWidget) -> QFrame:
    """Create a styled popup frame with rounded corners and selection
    highlighting.  Sets transient parent for Wayland compatibility.
    """
    popup = QFrame(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
    popup.setObjectName("completerPopup")
    # Set transient parent for Wayland (must be done before show)
    top = parent.window()
    if top is not None:
        # Create native window handle so transient parent can be set
        popup.winId()
        pw = popup.windowHandle()
        tw = top.windowHandle()
        if pw is not None and tw is not None:
            pw.setTransientParent(tw)
    popup.setStyleSheet(
        "#completerPopup {"
        "  background: palette(window);"
        "  border: 1px solid palette(mid);"
        "  border-radius: 8px;"
        "}"
        "QListWidget {"
        "  border: none;"
        "  background: transparent;"
        "}"
        "QListWidget::item:selected {"
        "  background: palette(highlight);"
        "  color: palette(highlighted-text);"
        "}"
        "QLineEdit {"
        "  border: none;"
        "  border-bottom: 1px solid palette(mid);"
        "  padding: 4px 6px;"
        "  background: transparent;"
        "}"
    )
    layout = QVBoxLayout(popup)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(2)
    return popup
