"""Spell-check highlighter — wavy red underlines for misspelled words."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import QTextEdit

from core.logging import setup_logging
from core.spell_checker import SpellChecker

_LOG = setup_logging("cutemd.spell_highlighter")

_WORD_RE = re.compile(r"\b\w{3,}\b", re.UNICODE)


class SpellHighlighter(QSyntaxHighlighter):
    """Underline misspelled words with a wavy red line."""

    def __init__(self, document, checker: SpellChecker) -> None:
        super().__init__(document)
        self._checker = checker
        self._fmt = QTextCharFormat()
        self._fmt.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SpellCheckUnderline
        )
        self._fmt.setUnderlineColor(Qt.GlobalColor.red)

    def highlightBlock(self, text: str) -> None:
        if not self._checker.available:
            _LOG.debug("block %d: checker not available", self.currentBlock().blockNumber())
            return

        skip = self._checker.skip_regions(text)
        errors = 0
        checked = 0
        for m in _WORD_RE.finditer(text):
            word = m.group(0)
            start = m.start()
            checked += 1
            if start in skip:
                continue
            if not self._checker.check(word):
                length = m.end() - start
                self.setFormat(start, length, self._fmt)
                errors += 1
        if checked:
            _LOG.debug("block %d: %d words, %d misspelled, langs=%s",
                       self.currentBlock().blockNumber(), checked, errors,
                       self._checker.langs)
