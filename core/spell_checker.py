"""Spell checker wrapper — optional pyenchant integration."""

from __future__ import annotations

import re
from typing import Any

from core.logging import setup_logging

_LOG = setup_logging("cutemd.spell_checker")

# Markdown tokens that should NOT be spell-checked.
_SKIP_PATTERNS: list[tuple[re.Pattern, int]] = [
    # Fenced code blocks (``` ... ```)
    (re.compile(r"```[\s\S]*?```"), 0),
    # Inline code (`...`)
    (re.compile(r"`[^`]+`"), 0),
    # URLs
    (re.compile(r"https?://\S+"), 0),
    # Wikilinks [[...]]
    (re.compile(r"\[\[[^\]]+\]\]"), 0),
    # Markdown links [...] (capture only the URL part)
    (re.compile(r"\]\(([^)]+)\)"), 1),
    # HTML tags
    (re.compile(r"<[^>]+>"), 0),
    # YAML frontmatter
    (re.compile(r"^---\s*\n.*?\n(?:---|\.\.\.)\s*\n", re.DOTALL), 0),
    # # Tags
    (re.compile(r"(?<=\s)#[\w\u0080-\uFFFF][\w\u0080-\uFFFF-]*"), 0),
]


class SpellChecker:
    """Optional spell checker backed by pyenchant."""

    def __init__(self, lang: str = "") -> None:
        self._dict: Any = None
        self._available = False
        self._lang = lang
        self._reload()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def lang(self) -> str:
        return self._lang

    def set_lang(self, lang: str) -> None:
        if lang != self._lang:
            self._lang = lang
            self._reload()

    def _reload(self) -> None:
        try:
            import enchant
        except ImportError:
            _LOG.debug("pyenchant not installed — spell check disabled")
            self._available = False
            return
        try:
            if self._lang:
                self._dict = enchant.Dict(self._lang)
            else:
                self._dict = enchant.Dict()
        except enchant.errors.DictNotFoundError:
            # Fall back to en_US when system default is unavailable
            if not self._lang:
                try:
                    self._dict = enchant.Dict("en_US")
                    self._lang = "en_US"
                except enchant.errors.DictNotFoundError:
                    _LOG.debug("dictionary not found for lang=%s", self._lang or "(default)")
                    self._available = False
                    return
            else:
                _LOG.debug("dictionary not found for lang=%s", self._lang)
                self._available = False
                return
        self._available = True

    def check(self, word: str) -> bool:
        if not self._available or self._dict is None:
            return True
        return bool(self._dict.check(word))

    def suggest(self, word: str) -> list[str]:
        if not self._available or self._dict is None:
            return []
        return self._dict.suggest(word) or []

    def skip_regions(self, text: str) -> set[int]:
        """Return a set of character positions that should be skipped."""
        skip: set[int] = set()
        for pattern, group in _SKIP_PATTERNS:
            for m in pattern.finditer(text):
                start = m.start(group)
                end = m.end(group)
                for i in range(start, end):
                    skip.add(i)
        return skip


def is_available() -> bool:
    try:
        import enchant  # noqa: F401
        return True
    except ImportError:
        return False
