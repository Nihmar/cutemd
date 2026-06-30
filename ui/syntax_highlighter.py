"""Markdown syntax highlighter using QSyntaxHighlighter."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from core.logging import setup_logging

_LOG = setup_logging("cutemd.syntax_highlighter")


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

    Uses per-line block state to track code fences and math
    blocks across line boundaries.
    """

    # --- Regex patterns ---
    HEADING_RE = re.compile(r"^#{1,6}\s.*$")
    BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
    ITALIC_RE = re.compile(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"
    )
    INLINE_CODE_RE = re.compile(r"`([^`]+)`")
    CODE_FENCE_RE = re.compile(r"^```.*$")
    MATH_FENCE_RE = re.compile(r"^\$\$")
    MATH_INLINE_RE = re.compile(r"\$[^$\n]+\$")
    LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
    FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\]")
    FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s+(.+)$")
    LIST_RE = re.compile(r"^(\s{0,3})([-*+]|\d+\.)\s")
    BLOCKQUOTE_RE = re.compile(r"^>\s?.*$")

    # Block state constants
    STATE_NORMAL = 0
    STATE_FENCE = 1
    STATE_MATH = 2
    STATE_FRONTMATTER = 3

    # Threshold above which inline patterns are skipped for performance.
    _LARGE_DOC_BLOCKS = 4000

    def __init__(self, parent=None, spell_checker=None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._theme = "dark"
        self._spell_checker = spell_checker
        self._spell_fmt = QTextCharFormat()
        self._spell_fmt.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SpellCheckUnderline
        )
        self._spell_fmt.setUnderlineColor(Qt.GlobalColor.red)
        self._needs_rehighlight = False
        self._build_formats()

    # ------------------------------------------------------------------
    # Theme support
    # ------------------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        """Switch between 'light' and 'dark' highlighting colors.

        If *theme* differs from current, rebuild formats and rehighlight.
        The ``_needs_rehighlight`` flag supports deferred application
        for tabs that are not currently visible.
        """
        if theme != self._theme:
            self._theme = theme
            self._build_formats()
            self.rehighlight()
            self._needs_rehighlight = False

    def set_theme_deferred(self, theme: str) -> None:
        """Update theme formats without triggering ``rehighlight()``.

        Useful when the editor tab is not currently visible — the
        actual rehighlight is deferred until ``ensure_rehighlighted()``
        is called.
        """
        if theme != self._theme:
            self._theme = theme
            self._build_formats()
            self._needs_rehighlight = True

    def ensure_rehighlighted(self) -> None:
        """Apply any pending theme rehighlight."""
        if self._needs_rehighlight:
            self._needs_rehighlight = False
            self.rehighlight()

    def _build_formats(self) -> None:
        if self._theme == "dark":
            self.heading_fmt = _make_format("#e06c75", bold=True)
            self.bold_fmt = _make_format("#d19a66", bold=True)
            self.italic_fmt = _make_format("#e5c07b", italic=True)
            self.inline_code_fmt = _make_format("#98c379", bg="#2c323c")
            self.code_fence_fmt = _make_format("#abb2bf", bg="#282c34")
            self.math_fmt = _make_format("#56b6c2")
            self.link_fmt = _make_format("#61afef")
            self.wikilink_fmt = _make_format("#56b6c2")
            self.footnote_ref_fmt = _make_format("#c678dd")
            self.footnote_def_fmt = _make_format("#98c379")
            self.list_fmt = _make_format("#c678dd")
            self.blockquote_fmt = _make_format("#5c6370")
            self.heading_global_fmt = _make_format("#e06c75", bold=True)
            self.frontmatter_key_fmt = _make_format("#56b6c2")     # teal keys
            self.frontmatter_val_fmt = _make_format("#abb2bf")     # dim values
            self.frontmatter_delim_fmt = _make_format("#5c6370")   # dim ---
        else:
            self.heading_fmt = _make_format("#a626a4", bold=True)
            self.bold_fmt = _make_format("#c18401", bold=True)
            self.italic_fmt = _make_format("#50a14f", italic=True)
            self.inline_code_fmt = _make_format("#e45649", bg="#f0f0f0")
            self.code_fence_fmt = _make_format("#383a42", bg="#fafafa")
            self.math_fmt = _make_format("#1a8ea8")
            self.link_fmt = _make_format("#4078f2")
            self.wikilink_fmt = _make_format("#1a8ea8")
            self.footnote_ref_fmt = _make_format("#0184bc")
            self.footnote_def_fmt = _make_format("#50a14f")
            self.list_fmt = _make_format("#0184bc")
            self.blockquote_fmt = _make_format("#a0a1a7")
            self.heading_global_fmt = _make_format("#a626a4", bold=True)
            self.frontmatter_key_fmt = _make_format("#a626a4")     # purple keys
            self.frontmatter_val_fmt = _make_format("#696c77")     # dim values
            self.frontmatter_delim_fmt = _make_format("#a0a1a7")   # dim ---

    # ------------------------------------------------------------------
    # Highlight a single block (line)
    # ------------------------------------------------------------------
    def highlightBlock(self, text: str) -> None:
        prev_state = self.previousBlockState()

        # --- Frontmatter tracking (first block only) ---
        stripped = text.strip()
        if prev_state == self.STATE_FRONTMATTER:
            self._fmt_frontmatter(text)
            self.setCurrentBlockState(
                self.STATE_NORMAL if stripped in ("---", "...") else self.STATE_FRONTMATTER
            )
            return

        if prev_state == self.STATE_NORMAL and self.currentBlock().blockNumber() == 0:
            if stripped == "---":
                self.setFormat(0, len(text), self.frontmatter_delim_fmt)
                self.setCurrentBlockState(self.STATE_FRONTMATTER)
                return

        # First block with default state (-1) — also check for frontmatter
        if self.currentBlock().blockNumber() == 0 and stripped == "---":
            self.setFormat(0, len(text), self.frontmatter_delim_fmt)
            self.setCurrentBlockState(self.STATE_FRONTMATTER)
            return

        # --- Code fence tracking (highest priority) ---
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

        # --- Math block tracking ($$...$$) ---
        if self.MATH_FENCE_RE.match(text.strip()):
            self.setFormat(0, len(text), self.math_fmt)
            if prev_state == self.STATE_MATH:
                self.setCurrentBlockState(self.STATE_NORMAL)
            else:
                self.setCurrentBlockState(self.STATE_MATH)
            return

        if prev_state == self.STATE_MATH:
            self.setFormat(0, len(text), self.math_fmt)
            self.setCurrentBlockState(self.STATE_MATH)
            return

        self.setCurrentBlockState(self.STATE_NORMAL)

        # Spell-check first — only sets underline style, won't touch foreground.
        # Applying it before syntax patterns lets the patterns overwrite the
        # default foreground / bold / italic while preserving the red underline.
        self._spell_check_block(text)

        # Syntax patterns (applied after spell-check so they win on colour).
        # Footnote definitions — whole-line pattern, before other inline rules.
        if text and text.lstrip()[:1] == '[':
            self._apply_rule(self.FOOTNOTE_DEF_RE, text, self.footnote_def_fmt)

        doc_large = (
            self.document() is not None
            and self.document().blockCount() > self._LARGE_DOC_BLOCKS
        )
        first_ch = text.lstrip()[:1] if text else ''
        if doc_large:
            if first_ch == '#':
                self._apply_rule(self.HEADING_RE, text, self.heading_fmt)
            if first_ch in ('-', '*', '+') or (first_ch and first_ch.isdigit()):
                self._apply_rule(self.LIST_RE, text, self.list_fmt)
        else:
            if first_ch == '#':
                self._apply_rule(self.HEADING_RE, text, self.heading_fmt)
            self._apply_rule(self.BOLD_RE, text, self.bold_fmt)
            self._apply_rule(self.ITALIC_RE, text, self.italic_fmt)
            self._apply_rule(self.INLINE_CODE_RE, text, self.inline_code_fmt)
            self._apply_rule(self.MATH_INLINE_RE, text, self.math_fmt)
            self._apply_rule(self.LINK_RE, text, self.link_fmt)
            self._apply_rule(self.WIKILINK_RE, text, self.wikilink_fmt)
            if first_ch in ('-', '*', '+') or (first_ch and first_ch.isdigit()):
                self._apply_rule(self.LIST_RE, text, self.list_fmt)
        self._apply_rule(self.FOOTNOTE_REF_RE, text, self.footnote_ref_fmt)
        if first_ch == '>':
            self._apply_rule(self.BLOCKQUOTE_RE, text, self.blockquote_fmt)

    _WORD_RE = re.compile(r"\b\w{3,}\b", re.UNICODE)

    def _spell_check_block(self, text: str) -> None:
        if self._spell_checker is None or not self._spell_checker.available:
            return
        skip = self._spell_checker.skip_regions(text)
        errors = 0
        for m in self._WORD_RE.finditer(text):
            word = m.group(0)
            start = m.start()
            if start in skip:
                continue
            ok = self._spell_checker.check(word)
            if not ok:
                self.setFormat(start, m.end() - start, self._spell_fmt)
                errors += 1
                _LOG.debug("spell err: %r (langs=%s)", word, self._spell_checker.langs)
        if errors:
            _LOG.debug("spell block %d: %d errors", self.currentBlock().blockNumber(), errors)

    def _fmt_frontmatter(self, text: str) -> None:
        """Highlight YAML key: value pairs in the frontmatter block."""
        if text.strip() in ("---", "..."):
            self.setFormat(0, len(text), self.frontmatter_delim_fmt)
            return
        # Highlight key (before :) and value (after :)
        m = re.match(r"(\s*)([^:]+)(:)(\s*)(.*)", text)
        if m:
            self.setFormat(m.start(1), m.end(1) - m.start(1), self.frontmatter_val_fmt)
            self.setFormat(m.start(2), m.end(2) - m.start(2), self.frontmatter_key_fmt)
            self.setFormat(m.start(3), 1, self.frontmatter_delim_fmt)
            self.setFormat(m.start(5), m.end(5) - m.start(5), self.frontmatter_val_fmt)
        else:
            self.setFormat(0, len(text), self.frontmatter_val_fmt)

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
