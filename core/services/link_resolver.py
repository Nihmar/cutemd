"""Pure path-based link/wikilink resolution — no Qt imports."""

from __future__ import annotations

from pathlib import Path

from core.logging import setup_logging

_LOG = setup_logging("cutemd.link_resolver")

_IMG_EXTS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}
)
_PDF_EXTS = frozenset({".pdf"})


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
    if target_path.suffix.lower() not in (".md", ".markdown"):
        candidates.append(base / (target + ".md"))
        candidates.append(base / (target + ".markdown"))
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
            if target_path.suffix.lower() not in (".md", ".markdown"):
                for ext in (".md", ".markdown"):
                    p2 = check_dir / (target + ext)
                    if p2.is_file():
                        return p2.resolve()
                for ext in _IMG_EXTS | _PDF_EXTS:
                    p2 = check_dir / (target + ext)
                    if p2.is_file():
                        return p2.resolve()

    # 4. Extension fallback in the base + attachments dir.
    if target_path.suffix.lower() not in _IMG_EXTS | _PDF_EXTS:
        for ext in _IMG_EXTS | _PDF_EXTS:
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

    return None
