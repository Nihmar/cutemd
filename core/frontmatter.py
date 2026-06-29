"""YAML frontmatter parsing shared across the application.

Every module that needs to read or strip frontmatter imports from
here so that the regex and parsing logic is defined once.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

# Matches the opening ---, the body, and closing --- or ...
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", re.DOTALL
)


def strip_frontmatter(text: str) -> str:
    """Remove the YAML frontmatter block, returning body only."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract the YAML frontmatter block as a dict.  Returns {} if none."""
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def frontmatter_offset(text: str) -> int:
    """Return how many lines the frontmatter block occupies."""
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return 0
    return m.group(0).count("\n")
