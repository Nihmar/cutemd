"""Markdown syntax highlighter using QSyntaxHighlighter."""

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


def _make_format(
    color: str | None = None,
    bold: bool = False,
    italic: bool = False,
    bg: str | None = None,
    font_family: str | None = None,
) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if color:
        fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    if bg:
        fmt.setBackground(QColor(bg))
    if font_family:
        fmt.setFontFamilies([font_family])
    return fmt


class MarkdownHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Markdown source text.

    Uses per-line block state to track code fences across line boundaries.
    """

    # --- Regex patterns ---
    HEADING_RE = re.compile(r"^#{1,6}\s.*$")
    BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
    ITALIC_RE = re.compile(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"
    )
    INLINE_CODE_RE = re.compile(r"`([^`]+)`")
    CODE_FENCE_RE = re.compile(r"^```.*$")
    LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    LIST_RE = re.compile(r"^(\s{0,3})([-*+]|\d+\.)\s")
    BLOCKQUOTE_RE = re.compile(r"^>\s?.*$")

    # Block state constants
    STATE_NORMAL = 0
    STATE_FENCE = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"  # default
        self._build_formats()

    # ------------------------------------------------------------------
    # Theme support
    # ------------------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        """Switch between 'light' and 'dark' highlighting colors."""
        if theme != self._theme:
            self._theme = theme
            self._build_formats()
            self.rehighlight()

    def _build_formats(self) -> None:
        if self._theme == "dark":
            self.heading_fmt = _make_format("#e06c75", bold=True)
            self.bold_fmt = _make_format("#d19a66", bold=True)
            self.italic_fmt = _make_format("#e5c07b", italic=True)
            self.inline_code_fmt = _make_format("#98c379", bg="#2c323c")
            self.code_fence_fmt = _make_format("#abb2bf", bg="#282c34")
            self.link_fmt = _make_format("#61afef")
            self.list_fmt = _make_format("#c678dd")
            self.blockquote_fmt = _make_format("#5c6370")
            self.heading_global_fmt = _make_format("#e06c75", bold=True)
        else:
            self.heading_fmt = _make_format("#a626a4", bold=True)
            self.bold_fmt = _make_format("#c18401", bold=True)
            self.italic_fmt = _make_format("#50a14f", italic=True)
            self.inline_code_fmt = _make_format("#e45649", bg="#f0f0f0")
            self.code_fence_fmt = _make_format("#383a42", bg="#fafafa")
            self.link_fmt = _make_format("#4078f2")
            self.list_fmt = _make_format("#0184bc")
            self.blockquote_fmt = _make_format("#a0a1a7")
            self.heading_global_fmt = _make_format("#a626a4", bold=True)

    # ------------------------------------------------------------------
    # Highlight a single block (line)
    # ------------------------------------------------------------------
    def highlightBlock(self, text: str) -> None:
        prev_state = self.previousBlockState()

        # --- Code fence tracking ---
        if self.CODE_FENCE_RE.match(text.strip()):
            fmt = self.code_fence_fmt
            self.setFormat(0, len(text), fmt)
            if prev_state == self.STATE_FENCE:
                self.setCurrentBlockState(self.STATE_NORMAL)
            else:
                self.setCurrentBlockState(self.STATE_FENCE)
            return

        if prev_state == self.STATE_FENCE:
            self.setFormat(0, len(text), self.code_fence_fmt)
            self.setCurrentBlockState(self.STATE_FENCE)
            return

        self.setCurrentBlockState(self.STATE_NORMAL)

        # --- Inline patterns ---
        self._apply_rule(self.HEADING_RE, text, self.heading_fmt)
        self._apply_rule(self.BOLD_RE, text, self.bold_fmt)
        self._apply_rule(self.ITALIC_RE, text, self.italic_fmt)
        self._apply_rule(self.INLINE_CODE_RE, text, self.inline_code_fmt)
        self._apply_rule(self.LINK_RE, text, self.link_fmt)
        self._apply_rule(self.LIST_RE, text, self.list_fmt)
        self._apply_rule(self.BLOCKQUOTE_RE, text, self.blockquote_fmt)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _apply_rule(
        self, pattern: "re.Pattern[str]", text: str, fmt: QTextCharFormat
    ) -> None:
        for m in pattern.finditer(text):
            start = m.start()
            length = m.end() - start
            self.setFormat(start, length, fmt)
