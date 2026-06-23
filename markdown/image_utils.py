"""Image-related utilities for Markdown HTML processing.

Pure functions — no Qt/UI dependencies. Image size lookup is injected
as a callback by the UI layer.
"""

import re
from pathlib import Path
from typing import Callable

_IMG_EXTS_RE = re.compile(r"\.(png|jpg|jpeg|gif|bmp|svg|webp|ico)$", re.I)
_IMG_DIMS_RE = re.compile(r'(<img\s+)(src="([^"]*)")')
_PARA_IMG_RE = re.compile(r"<p>\s*(<a\b[^>]*></a>)?\s*(<img\b[^>]+>)\s*</p>")


def needs_loading(src: str) -> bool:
    if not src or "://" in src or src.startswith("data:") or src.startswith("file:"):
        return False
    return bool(_IMG_EXTS_RE.search(src))


def _search_image(filename: str, start_dir: Path, max_up: int = 3) -> Path | None:
    """Last-resort recursive search for *filename*.

    Walks up to *max_up* ancestor levels from *start_dir*, scanning
    descendants up to depth 3 at each level.  Stops at the filesystem
    root or the user's home directory.

    This is intentionally narrow — the configured images directory
    should be the primary lookup path.
    """
    target = filename.lower()
    seen: set[Path] = set()
    home = Path.home().resolve()

    current = start_dir.resolve()
    for _ in range(max_up):
        stack = [(current, 0)]
        while stack:
            d, depth = stack.pop()
            if d in seen:
                continue
            seen.add(d)
            try:
                for entry in d.iterdir():
                    if entry.is_file() and entry.name.lower() == target:
                        return entry.resolve()
                    if entry.is_dir() and depth < 3:
                        stack.append((entry, depth + 1))
            except PermissionError:
                continue

        if current == home or current.parent == current:
            break
        current = current.parent
    return None


def resolve_image_path(
    src: str, base_dir: Path, images_dir: Path | None = None
) -> Path | None:
    p = Path(src)
    if not needs_loading(src) or p.is_absolute():
        return p if p.is_file() else None

    # 1. Same directory as the Markdown file.
    resolved = (base_dir / p).resolve()
    if resolved.is_file():
        return resolved

    # 2. Configured images directory (fast, no recursion).
    if images_dir is not None:
        resolved = (images_dir / p.name).resolve()
        if resolved.is_file():
            return resolved

    # 3. Limited recursive fallback.
    return _search_image(p.name, base_dir)


# Signature: (path_str, max_width) -> (width, height) or None
SizeProvider = Callable[[str, int], tuple[int, int] | None]


def add_img_dimensions(
    html: str,
    base_dir: Path,
    max_width: int,
    get_size: SizeProvider,
    images_dir: Path | None = None,
) -> str:
    """Resolve local image paths to file:// URLs and add width/height."""

    def _repl(m: re.Match) -> str:
        prefix = m.group(1)
        src_attr = m.group(2)
        src = m.group(3)
        # Leave external/existing absolute URLs alone.
        if not needs_loading(src) or Path(src).is_absolute():
            return m.group(0)
        resolved = resolve_image_path(src, base_dir, images_dir)
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
