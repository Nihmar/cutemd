"""Inverted-index search for vault Markdown files.

Builds a word-to-file-set index from VaultScanner ``file_content``
signals, then answers plain-text queries in O(log n) by intersecting
file sets.  Falls back to linear scan for regex queries.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from core.logging import setup_logging

_LOG = setup_logging("cutemd.search_index")

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_STOP_WORDS = frozenset({
    "the", "is", "at", "which", "on", "a", "an", "and", "or", "but",
    "in", "with", "for", "of", "to", "by", "from", "as", "be", "was",
    "are", "it", "its", "not", "no", "this", "that", "if", "so",
    "we", "you", "he", "she", "they", "do", "does", "has", "have",
    "had", "can", "will", "would", "could", "should", "may",
})


class SearchIndex:
    """In-memory inverted index: word → set of file paths."""

    def __init__(self) -> None:
        self._index: dict[str, set[Path]] = defaultdict(set)
        self._file_count = 0

    @property
    def file_count(self) -> int:
        return self._file_count

    def add_file(self, path: Path, text: str) -> None:
        """Index all words in *text* for the given *path*."""
        if not text:
            return
        lower = text.lower()
        words = frozenset(
            w for w in _WORD_RE.findall(lower)
            if len(w) > 1 and w not in _STOP_WORDS
        )
        for word in words:
            self._index[word].add(path)
        self._file_count += 1

    def remove_file(self, path: Path) -> None:
        """Remove *path* from every word entry (on file deletion/rename)."""
        for word, files in self._index.items():
            files.discard(path)
        self._file_count = max(0, self._file_count - 1)

    def query(self, words: str) -> set[Path] | None:
        """Return the set of files containing ALL query words.

        Returns ``None`` when the index has no data (caller should
        fall back to a linear scan).  Returns an empty set when the
        query words produce zero matches.
        """
        tokens = [t for t in _WORD_RE.findall(words.lower()) if t not in _STOP_WORDS]
        if not tokens:
            return None
        if not self._index:
            return None
        # Start with the smallest set to minimise intersection work.
        candidates = sorted(
            (self._index.get(t, set()) for t in tokens),
            key=len,
        )
        result = candidates[0]
        if not result:
            return result  # empty → no matches
        for other in candidates[1:]:
            result = result.intersection(other)
            if not result:
                break
        return result

    def clear(self) -> None:
        self._index.clear()
        self._file_count = 0
