"""Registry of Markdown formatting actions — shared by toolbar and context menu."""

from __future__ import annotations

HEADING_PREFIXES: list[tuple[str, str]] = [
    ("# ", "H1"),
    ("## ", "H2"),
    ("### ", "H3"),
    ("#### ", "H4"),
    ("##### ", "H5"),
    ("###### ", "H6"),
]

TOOLBAR_ITEMS: list[tuple[str, str, str]] = [
    # (icon_name, syntax, tooltip_key)
    ("list-unordered", "- ",       "Unordered list (- )"),
    ("list-ordered",   "1. ",      "Ordered list (1. )"),
    ("list-task",      "- [ ] ",   "Task list (- [ ])"),
    ("quote",          "> ",       "Blockquote (> )"),
    ("code-block",     "```",      "Code block (```)"),
    ("table",          "\n| Col 1 | Col 2 |\n|------|------|\n|      |      |\n", "Insert table"),
    ("hr",             "---\n",    "Horizontal rule (---)"),
    ("bold",           "**",       "Bold (**text**)"),
    ("italic",         "*",        "Italic (*text*)"),
    ("strikethrough",  "~~",       "Strikethrough (~~text~~)"),
    ("code",           "`",        "Inline code (`text`)"),
    ("link",           "[]()",     "Insert link ([]())"),
]

CONTEXT_MENU_ITEMS: list[tuple[str, str, str, str]] = [
    # (category, icon, label, syntax)
    ("inline", "bold",             "&Bold",           "**"),
    ("inline", "italic",           "&Italic",         "*"),
    ("inline", "strikethrough",    "&Strikethrough",  "~~"),
    ("inline", "code",             "Inline &Code",    "`"),
    ("list",   "list-unordered",   "&Unordered list", "- "),
    ("list",   "list-ordered",     "&Ordered list",   "1. "),
    ("list",   "list-task",        "&Task list",      "- [ ] "),
    ("block",  "quote",            "Block&quote",     "> "),
    ("block",  "code-block",       "Code &block",     "```"),
    ("block",  "table",            "&Table",          "\n| Col 1 | Col 2 |\n|------|------|\n|      |      |\n"),
    ("block",  "hr",               "&Horizontal rule","---\n"),
    ("insert", "link",             "&Link",           "[]()"),
]
