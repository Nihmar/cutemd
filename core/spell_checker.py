"""Spell checker wrapper — optional pyenchant integration."""

from __future__ import annotations

import re
from pathlib import Path
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
    """Optional spell checker backed by pyenchant.  Supports multiple
    simultaneous dictionaries (e.g. en_US + it_IT)."""

    def __init__(self, langs: list[str] | None = None) -> None:
        self._dicts: list[Any] = []
        self._available = False
        self._langs: list[str] = []
        self._reload(langs or [])

    @property
    def available(self) -> bool:
        return self._available

    @property
    def langs(self) -> list[str]:
        return list(self._langs)

    def set_langs(self, langs: list[str]) -> None:
        if langs != self._langs:
            self._reload(langs)

    def _reload(self, langs: list[str]) -> None:
        self._available = False
        self._dicts = []
        self._langs = []
        try:
            import enchant
        except ImportError:
            _LOG.debug("pyenchant not installed — spell check disabled")
            return

        if not langs:
            try:
                d = enchant.Dict()
                self._dicts.append(d)
                self._langs.append("default")
            except enchant.errors.DictNotFoundError:
                try:
                    d = enchant.Dict("en_US")
                    self._dicts.append(d)
                    self._langs.append("en_US")
                except enchant.errors.DictNotFoundError:
                    pass
        else:
            for lang in langs:
                try:
                    d = enchant.Dict(lang)
                    self._dicts.append(d)
                    self._langs.append(lang)
                except enchant.errors.DictNotFoundError:
                    _LOG.debug("dictionary not found: %s (install it in Settings)", lang)

        if self._dicts:
            self._available = True
            _LOG.debug("spell checker loaded: langs=%s", self._langs)

    def check(self, word: str) -> bool:
        if not self._available:
            return True
        return any(d.check(word) for d in self._dicts)

    def suggest(self, word: str) -> list[str]:
        if not self._available:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for d in self._dicts:
            for s in (d.suggest(word) or []):
                if s not in seen:
                    seen.add(s)
                    result.append(s)
        return result

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


def _user_dicts_dir() -> Path:
    from PySide6.QtCore import QStandardPaths
    data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    return Path(data) / "dictionaries"


_dict_path_set = False


def _ensure_env_dict_path() -> None:
    global _dict_path_set
    import os
    dirs = str(_user_dicts_dir())
    os.makedirs(dirs, exist_ok=True)
    existing = os.environ.get("ENCHANT_MYSPELL_DICT_PATH", "")
    if existing:
        dirs = dirs + os.pathsep + existing
    os.environ["ENCHANT_MYSPELL_DICT_PATH"] = dirs
    if not _dict_path_set:
        _LOG.debug("ENCHANT_MYSPELL_DICT_PATH=%s", dirs)
        _dict_path_set = True
