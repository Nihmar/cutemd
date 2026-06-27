"""Constant definitions shared across all packages.

All file-extension sets, size thresholds, and shortcut categories
are defined here once so that every module imports from a single
source of truth.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# File extension sets
# ---------------------------------------------------------------------------

MD_EXTS: frozenset[str] = frozenset({".md", ".markdown"})
IMG_EXTS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}
)
PDF_EXTS: frozenset[str] = frozenset({".pdf"})
DOC_EXTS: frozenset[str] = frozenset({".docx", ".xlsx", ".pptx", ".cbz", ".epub"})
CSV_EXTS: frozenset[str] = frozenset({".csv", ".tsv"})

# ---------------------------------------------------------------------------
# Size / line thresholds
# ---------------------------------------------------------------------------

LARGE_FILE_THRESHOLD: int = 1_048_576  # 1 MB — disable preview & highlighting
BROKEN_LINK_LINE_LIMIT: int = 2_000  # max lines for broken-link highlighting

# ---------------------------------------------------------------------------
# Keyboard shortcut categories
# ---------------------------------------------------------------------------

SHORTCUT_CATEGORIES: dict[str, str] = {
    "act_open_folder": "File",
    "act_close_folder": "File",
    "act_new": "File",
    "act_save": "File",
    "act_save_as": "File",
    "act_close_tab": "File",
    "act_exit": "File",
    "act_undo": "Edit",
    "act_redo": "Edit",
    "act_find": "Edit",
    "act_find_files": "Edit",
    "act_replace_files": "Edit",
    "act_toggle_preview": "View",
    "act_toggle_split": "View",
    "act_toggle_tree": "View",
    "act_toggle_statusbar": "View",
    "act_zoom_in": "View",
    "act_zoom_out": "View",
    "act_zoom_reset": "View",
    "act_zoom_preview_in": "View",
    "act_zoom_preview_out": "View",
    "act_webdav_sync": "File",
    "act_check_update": "Help",
    "act_command_palette": "Help",
    "act_settings": "Settings",
    "act_shortcuts": "Help",
}

CATEGORY_ORDER: dict[str, int] = {
    "File": 0,
    "Edit": 1,
    "View": 2,
    "Settings": 3,
    "Help": 4,
    "Other": 99,
}
