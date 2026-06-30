"""Spell checker wrapper — optional pyenchant integration."""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from threading import Lock
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
    # Footnote references [^label]
    (re.compile(r"\[\^[^\]]+\]"), 0),
    # Footnote definitions [^label]: ...
    (re.compile(r"^\[\^[^\]]+\]:\s*.+$", re.MULTILINE), 0),
]


class SpellChecker:
    """Optional spell checker backed by pyenchant.  Supports multiple
    simultaneous dictionaries (e.g. en_US + it_IT) plus a per-folder
    custom word list stored in ``.cutemd/custom_dict.txt``."""

    _CHECK_CACHE_SIZE = 2000

    def __init__(self, langs: list[str] | None = None, *, lazy: bool = True) -> None:
        self._dicts: list[Any] = []
        self._available = False
        self._langs: list[str] = []
        self._custom_words: set[str] = set()
        self._custom_dict_path: Path | None = None
        self._check_cache: OrderedDict[str, bool] = OrderedDict()
        self._cache_lock = Lock()
        self._loaded = False
        self._pending_langs: list[str] = list(langs) if langs else []
        if not lazy:
            self._ensure_loaded()

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    @property
    def langs(self) -> list[str]:
        self._ensure_loaded()
        return list(self._langs)

    def set_langs(self, langs: list[str]) -> None:
        if langs != self._langs and langs != self._pending_langs:
            self._pending_langs = list(langs)
            if self._loaded:
                self._reload(langs)

    def _ensure_loaded(self) -> None:
        """Perform the lazy import + dictionary load if not done yet."""
        if self._loaded:
            return
        self._loaded = True
        self._reload(self._pending_langs)

    def _reload(self, langs: list[str]) -> None:
        self._available = False
        self._dicts = []
        self._langs = []
        self._invalidate_cache()
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
        """Return True if *word* is correctly spelled (hunspell OR custom dict).

        Uses a thread-safe LRU cache to avoid repeated dictionary lookups.
        """
        # Always accept words in the custom dictionary (no cache — rarely called).
        if word in self._custom_words:
            return True
        self._ensure_loaded()
        if not self._available:
            return True

        with self._cache_lock:
            cached = self._check_cache.get(word)
            if cached is not None:
                # Move to end (most recently used).
                self._check_cache.move_to_end(word)
                return cached

        result = any(d.check(word) for d in self._dicts)
        with self._cache_lock:
            self._check_cache[word] = result
            self._check_cache.move_to_end(word)
            if len(self._check_cache) > self._CHECK_CACHE_SIZE:
                self._check_cache.popitem(last=False)
        return result

    def _invalidate_cache(self) -> None:
        """Clear the check cache (called when dictionaries change)."""
        with self._cache_lock:
            self._check_cache.clear()

    def suggest(self, word: str) -> list[str]:
        self._ensure_loaded()
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

    def load_custom_dict(self, folder_path: Path) -> None:
        """Load the custom word list from ``<folder>/.cutemd/custom_dict.txt``.

        Words are stored one-per-line, case-sensitive, UTF-8.
        """
        self._custom_words = set()
        self._invalidate_cache()
        path = folder_path / ".cutemd" / "custom_dict.txt"
        self._custom_dict_path = path
        if not path.is_file():
            return
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                w = line.strip()
                if w:
                    self._custom_words.add(w)
            _LOG.debug("custom dict loaded: %d words from %s", len(self._custom_words), path)
        except OSError:
            _LOG.debug("custom dict read error: %s", path, exc_info=True)

    def add_word(self, word: str) -> None:
        """Add *word* to the custom dictionary and persist it to disk."""
        if word in self._custom_words:
            return
        self._custom_words.add(word)
        self._invalidate_cache()
        if self._custom_dict_path is None:
            _LOG.debug("add_word(%r): no custom dict path set", word)
            return
        try:
            self._custom_dict_path.parent.mkdir(parents=True, exist_ok=True)
            with self._custom_dict_path.open("a", encoding="utf-8") as f:
                f.write(word + "\n")
            _LOG.debug("custom dict: added %r", word)
        except OSError:
            _LOG.debug("custom dict write error", exc_info=True)

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
