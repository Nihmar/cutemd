"""Per-folder initialisation logic — pure, no Qt imports."""

from __future__ import annotations


def default_folder_config(
    global_theme: str,
    editor_font_family: str,
    editor_font_size: int,
    preview_font_family: str,
    preview_font_size: int,
    attachments_dir: str = "images",
) -> dict[str, object]:
    """Return the default per-folder settings dict, seeded from global values."""
    return {
        "theme": global_theme,
        "editor_font_family": editor_font_family,
        "editor_font_size": editor_font_size,
        "preview_font_family": preview_font_family,
        "preview_font_size": preview_font_size,
        "attachments_dir": attachments_dir,
    }
