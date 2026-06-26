"""Recent folders management — pure logic, no Qt imports."""

from __future__ import annotations

from pathlib import Path


def update_recent_folders(
    current: list[str], new_path: str, max_items: int = 10
) -> list[str]:
    """Add *new_path* to the front of the list, removing duplicates."""
    result = [p for p in current if p != new_path]
    result.insert(0, new_path)
    return result[:max_items]
