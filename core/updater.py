"""Auto-update logic — pure, no Qt imports."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import requests

from core.logging import setup_logging

_LOG = setup_logging("cutemd.updater")

_API_URL = "https://api.github.com/repos/Nihmar/cutemd/releases/latest"

# Patterns to match the best asset per platform (first match wins)
_ASSET_PATTERNS: dict[str, list[str]] = {
    "windows": [r"CuteMD_Setup\.exe$"],
    "linux": [r"\.AppImage$", r"\.deb$", r"\.rpm$"],
}


@dataclass(frozen=True)
class UpdateInfo:
    latest_tag: str
    latest_version: tuple[int, int, int]
    download_url: str
    asset_name: str
    asset_size: int
    release_notes: str
    platform_key: str  # "windows" | "linux"


def _parse_version(tag: str) -> tuple[int, int, int] | None:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _detect_platform_key() -> str:
    return "windows" if sys.platform == "win32" else "linux"


def _pick_asset(assets: list[dict], platform: str) -> tuple[str, str, int] | None:
    patterns = _ASSET_PATTERNS.get(platform, [])
    for pat in patterns:
        for a in assets:
            if re.search(pat, a.get("name", ""), re.IGNORECASE):
                return (a["name"], a["browser_download_url"], a.get("size", 0))
    return None


def check_for_update(current_version: str) -> UpdateInfo | None:
    """Query the GitHub releases API.

    Returns ``UpdateInfo`` if a newer version is found and a matching
    platform asset exists, or ``None`` when already up-to-date or on
    any error (network, unparseable response, missing asset).
    """
    try:
        resp = requests.get(_API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None
    if not isinstance(data, dict):
        return None

    tag = data.get("tag_name", "")
    ver = _parse_version(tag)
    if ver is None:
        return None
    cur = _parse_version(current_version)
    if cur is None:
        return None
    if ver <= cur:
        return None

    platform = _detect_platform_key()
    asset = _pick_asset(data.get("assets", []), platform)
    if asset is None:
        return None

    return UpdateInfo(
        latest_tag=tag,
        latest_version=ver,
        download_url=asset[1],
        asset_name=asset[0],
        asset_size=asset[2],
        release_notes=data.get("body", ""),
        platform_key=platform,
    )


def download_release(
    update_info: UpdateInfo,
    dest_dir: Path | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path | None:
    """Download the release asset.

    Parameters
    ----------
    update_info:
        The update info returned by :func:`check_for_update`.
    dest_dir:
        Target directory (defaults to ``~/Downloads``).
    progress_callback:
        Optional ``(downloaded_bytes, total_bytes)`` — called for each chunk.

    Returns the local ``Path`` on success, or ``None`` on failure.
    """
    if dest_dir is None:
        dest_dir = Path.home() / "Downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / update_info.asset_name

    try:
        with requests.get(update_info.download_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(downloaded, total)
        return dest
    except requests.RequestException as e:
        _LOG.debug("download_release: %s", e)
        return None
