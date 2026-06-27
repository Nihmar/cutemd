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

from PySide6.QtCore import QEvent, QObject, QRect, QStringListModel, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QCompleter, QPlainTextEdit

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
        self._tag_model = QStringListModel(self)
        self._tag_completer = QCompleter(self._tag_model, self)
        self._tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tag_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._tag_completer.activated.connect(self._on_tag_completed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_settings(self, settings: dict[str, Any]) -> None:
        self._cfg.update(settings)

    def set_tag_list(self, tags: list[str]) -> None:
        """Update the tag list used for Ctrl+Space autocomplete."""
        self._tag_list = sorted(set(tags))
        self._tag_model.setStringList(self._tag_list)

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is not self._editor or event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        key_event: QKeyEvent = event  # type: ignore[assignment]

        # Tag autocomplete: Ctrl+Space after #
        if (key_event.key() == Qt.Key.Key_Space
                and key_event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            return self._show_tag_completer()

        return self._handle_key(key_event)

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
    # Tag autocomplete (Ctrl+Space after #)
    # ------------------------------------------------------------------

    def _show_tag_completer(self) -> bool:
        """Show a QCompleter popup with tags matching the partial text
        after ``#``.
        """
        if not self._tag_list:
            return False

        cursor = self._editor.textCursor()
        pos = cursor.position()
        block_text = cursor.block().text()
        pos_in_block = cursor.positionInBlock()

        # Walk backwards from cursor to find the #
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

        # Extract partial tag text after #
        partial = block_text[hash_pos + 1:pos_in_block]
        prefix = "#" + partial

        # Filter tags matching the partial text
        matching = [t for t in self._tag_list
                    if partial.lower() in t.lower()]
        if not matching:
            return False

        self._tag_model.setStringList(matching)
        self._tag_completer.setCompletionPrefix(prefix)

        # Show popup at the # position
        block_start = cursor.block().position()
        cursor_rect = self._editor.cursorRect(cursor)
        popup_rect = QRect(
            cursor_rect.x(),
            cursor_rect.y() + cursor_rect.height() + 2,
            200,
            min(len(matching) * 20 + 4, 200),
        )
        self._tag_completer.complete(popup_rect)

        # Adjust popup width to longest tag
        popup = self._tag_completer.popup()
        if popup:
            popup.setMinimumWidth(180)

        return True

    def _on_tag_completed(self, text: str) -> None:
        """Replace the partial tag after # with the selected completion."""
        cursor = self._editor.textCursor()
        pos_in_block = cursor.positionInBlock()
        block = cursor.block()
        block_text = block.text()

        # Find the # position
        hash_pos = -1
        for i in range(pos_in_block - 1, -1, -1):
            if block_text[i] == "#":
                hash_pos = i
                break
            if block_text[i].isspace():
                break

        if hash_pos < 0:
            return

        # Select from # to cursor and replace with #tag
        block_start = block.position()
        cursor.setPosition(block_start + hash_pos)
        cursor.setPosition(block_start + pos_in_block, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("#" + text)
        self._editor.setTextCursor(cursor)
