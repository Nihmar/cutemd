"""Image-related utilities for Markdown HTML processing.

Pure functions — no Qt/UI dependencies. Image size lookup is injected
as a callback by the UI layer.
"""

import re
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

_IMG_EXTS_RE = re.compile(r"\.(png|jpg|jpeg|gif|bmp|svg|webp|ico)$", re.I)
_IMG_DIMS_RE = re.compile(r'(<img\s+)(src="([^"]*)")')
_PARA_IMG_RE = re.compile(r"<p>\s*(<a\b[^>]*></a>)?\s*(<img\b[^>]+>)\s*</p>")


def needs_loading(src: str) -> bool:
    if not src or "://" in src or src.startswith("data:") or src.startswith("file:"):
        return False
    return bool(_IMG_EXTS_RE.search(src))


def build_file_index(root: Path) -> dict[str, list[Path]]:
    """Build a filename → [resolved_path] index for a vault root.

    Skips hidden directories (like .cutemd). Call once per render and
    pass the result to ``resolve_image_path`` to avoid repeated full
    directory walks.
    """
    index: dict[str, list[Path]] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        key = p.name.lower()
        index.setdefault(key, []).append(p.resolve())
    return index


def _rglob_search(
    filename: str, root: Path, file_index: dict[str, list[Path]] | None = None
) -> Path | None:
    """Search for *filename* under *root* using the pre-built index."""
    target = filename.lower()
    if file_index is not None:
        for p in file_index.get(target, []):
            return p
        return None
    # Fallback: full recursive search (should rarely be used now).
    for p in root.rglob("*"):
        if p.is_file() and p.name.lower() == target:
            try:
                if any(part.startswith(".") for part in p.relative_to(root).parts):
                    continue
            except ValueError:
                pass
            return p.resolve()
    return None


def resolve_image_path(
    src: str,
    base_dir: Path,
    attachments_dir: Path | None = None,
    file_index: dict[str, list[Path]] | None = None,
) -> Path | None:
    src = unquote(src)
    p = Path(src)
    if not needs_loading(src) or p.is_absolute():
        return p if p.is_file() else None

    # 1. Same directory as the Markdown file.
    resolved = (base_dir / p).resolve()
    if resolved.is_file():
        return resolved

    # 2. Configured images directory.
    if attachments_dir is not None:
        resolved = (attachments_dir / p.name).resolve()
        if resolved.is_file():
            return resolved

    # 3. Vault-wide search using the pre-built index.
    vault_root = attachments_dir.parent if attachments_dir is not None else base_dir
    return _rglob_search(p.name, vault_root, file_index)


# Signature: (path_str, max_width) -> (width, height) or None
SizeProvider = Callable[[str, int], tuple[int, int] | None]


def add_img_dimensions(
    html: str,
    base_dir: Path,
    max_width: int,
    get_size: SizeProvider,
    attachments_dir: Path | None = None,
    file_index: dict[str, list[Path]] | None = None,
) -> str:
    """Resolve local image paths to file:// URLs and add width/height."""

    def _repl(m: re.Match) -> str:
        prefix = m.group(1)
        src_attr = m.group(2)
        src = m.group(3)
        # Leave external/existing absolute URLs alone.
        if not needs_loading(src) or Path(src).is_absolute():
            return m.group(0)
        resolved = resolve_image_path(src, base_dir, attachments_dir, file_index)
        if resolved is None:
            return m.group(0)
        # Embed an absolute file:// URL so Qt never needs to resolve it.
        file_url = resolved.resolve().as_uri()
        new_src = f'src="{file_url}"'
        dims = get_size(str(resolved), max_width)
        if dims is None:
            return f"{prefix}{new_src}"
        w, h = dims
        return f'{prefix}{new_src} width="{w}" height="{h}"'

    return _IMG_DIMS_RE.sub(_repl, html)


def fix_image_paragraphs(html: str) -> str:
    return _PARA_IMG_RE.sub(
        r'<p style="margin-top:0px;margin-bottom:0px;line-height:0px;">\1\2</p>',
        html,
    )
