"""Build line→anchor mappings from markdown-it token streams — pure logic."""

from __future__ import annotations

from markdown_it import MarkdownIt


def build_line_anchor_map(md: MarkdownIt, text: str) -> list[int]:
    """Build a mapping from editor line numbers to preview heading anchors.

    Parses the markdown-it token stream to find headings, then for each
    editor line determines which heading's anchor should be the scroll
    target. For lines between headings, uses the nearest heading above.

    Returns a list of ``anchor_index`` values, one per line of *text*.
    """
    from markdown.tools import BLOCK_OPEN_TYPES

    tokens = md.parse(text)
    entries: list[tuple[int, int, int]] = []
    anchor_idx = 0
    for token in tokens:
        if token.type in BLOCK_OPEN_TYPES and token.map:
            start, end = token.map
            if start < end:
                entries.append((start, end, anchor_idx))
                anchor_idx += 1

    total_lines = len(text.split("\n"))
    mapping = [0] * max(total_lines, 1)
    last_anchor = anchor_idx - 1 if anchor_idx > 0 else 0
    entries.sort(key=lambda x: x[0])

    for line in range(total_lines):
        best: int | None = None
        best_width = float("inf")
        for start, end, aidx in entries:
            if line < start:
                break
            if start <= line < end:
                width = end - start
                if width < best_width:
                    best_width = width
                    best = aidx
        if best is not None:
            mapping[line] = best
        else:
            prev: int = last_anchor
            for s, e, aidx in entries:
                if line < s:
                    break
                prev = aidx
            mapping[line] = prev
    return mapping
