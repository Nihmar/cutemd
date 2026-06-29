"""Link/wikilink resolution and anchor mapping — pure logic, no Qt imports."""

from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt

from core.constants import DOC_EXTS, IMG_EXTS, MD_EXTS, PDF_EXTS
from core.frontmatter import parse_frontmatter
from core.logging import setup_logging

_LOG = setup_logging("cutemd.link_resolution")


# ---------------------------------------------------------------------------
# Link / wikilink path resolution
# ---------------------------------------------------------------------------


def resolve_link_target(
    target: str,
    source_dir: Path,
    attachments_dir: Path | None = None,
    *,
    quick: bool = False,
) -> Path | None:
    """Resolve a link/wikilink target to an absolute ``Path``, or ``None``.

    Parameters
    ----------
    target:
        The raw link target (e.g. ``"My Note"``, ``"../image.png"``).
    source_dir:
        Directory of the file containing the link.
    attachments_dir:
        Optional per-folder attachments directory.
    quick:
        If ``True``, skip the full recursive ``rglob`` search (used for
        link highlighting — the click handler still does the full search).
    """
    _LOG.debug("resolve_link_target: %s", target)
    target_path = Path(target)
    if target_path.is_absolute():
        return target_path if target_path.exists() else None

    base = source_dir

    # 1. Same directory as the source file.
    candidates = [base / target_path]
    if target_path.suffix.lower() not in MD_EXTS:
        candidates.append(base / (target + ".md"))
        candidates.append(base / (target + ".markdown"))
    # When the target has no extension, also try document formats.
    if not target_path.suffix:
        for ext in DOC_EXTS | IMG_EXTS | PDF_EXTS:
            candidates.append(base / (target + ext))
    for p in candidates:
        if p.is_file():
            return p.resolve()

    # 2. Attachments directory (by filename).
    if attachments_dir is not None:
        candidate = attachments_dir / target_path.name
        if candidate.is_file():
            return candidate.resolve()

    vault_root = (
        attachments_dir.parent.resolve()
        if attachments_dir is not None
        else None
    )

    # 3. Proximity search: walk up the directory tree (max 5 levels).
    if vault_root is not None:
        check_dir = base.resolve()
        for _ in range(5):
            if check_dir == vault_root or check_dir.parent == check_dir:
                break
            check_dir = check_dir.parent
            pc = check_dir / target_path
            if pc.is_file():
                return pc.resolve()
            if target_path.suffix.lower() not in MD_EXTS:
                for ext in MD_EXTS:
                    p2 = check_dir / (target + ext)
                    if p2.is_file():
                        return p2.resolve()
                for ext in IMG_EXTS | PDF_EXTS | DOC_EXTS:
                    p2 = check_dir / (target + ext)
                    if p2.is_file():
                        return p2.resolve()

    # 4. Extension fallback in the base + attachments dir.
    if target_path.suffix.lower() not in IMG_EXTS | PDF_EXTS | DOC_EXTS:
        for ext in IMG_EXTS | PDF_EXTS | DOC_EXTS:
            p = base / (target + ext)
            if p.is_file():
                return p.resolve()
            if attachments_dir is not None:
                p2 = attachments_dir / (target_path.name + ext)
                if p2.is_file():
                    return p2.resolve()

    # 5. Full recursive search of the vault root (skipped for quick checks).
    if quick:
        return None

    search_root = vault_root if vault_root is not None else base
    target_name = target_path.name.lower()
    try:
        for p in search_root.rglob("*"):
            if p.is_file() and p.name.lower() == target_name:
                try:
                    if any(
                        part.startswith(".")
                        for part in p.relative_to(search_root).parts
                    ):
                        continue
                except ValueError:
                    pass
                return p.resolve()
    except PermissionError:
        pass

    # 6. Alias resolution — check frontmatter aliases in all .md files.
    if not quick and vault_root is not None:
        try:
            for p in vault_root.rglob("*.md"):
                if p.is_file():
                    try:
                        text = p.read_text(encoding="utf-8")
                    except OSError:
                        continue
                    fm = parse_frontmatter(text)
                    aliases = fm.get("aliases", [])
                    if isinstance(aliases, str):
                        aliases = [aliases]
                    if isinstance(aliases, list) and target in aliases:
                        return p.resolve()
                    # Also check the "alias" singular form
                    alias_single = fm.get("alias", None)
                    if isinstance(alias_single, str) and alias_single == target:
                        return p.resolve()
        except PermissionError:
            pass

    return None


# ---------------------------------------------------------------------------
# Line → preview-anchor mapping
# ---------------------------------------------------------------------------


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
