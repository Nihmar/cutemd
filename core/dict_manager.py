"""Dictionary download manager for spell-check dictionaries.

Downloads hunspell dictionaries from ``wooorm/dictionaries`` and
stores them in a user-writable directory that works in both dev
and PyInstaller builds.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, QThread, Signal

from core.logging import setup_logging

_LOG = setup_logging("cutemd.dict_manager")

# UI language code → hunspell dictionary code
AVAILABLE_DICTS: dict[str, str] = {
    "en": "en_US",
    "de": "de_DE",
    "es": "es_ES",
    "fr": "fr_FR",
    "it": "it_IT",
    "nl": "nl_NL",
    "pt": "pt_PT",
}

_GITHUB_BASE = (
    "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/"
)


def _dicts_dir() -> Path:
    data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    return Path(data) / "dictionaries"


def _manifest_path() -> Path:
    return _dicts_dir() / "manifest.json"


def load_manifest() -> dict[str, bool]:
    p = _manifest_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_manifest(data: dict[str, bool]) -> None:
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


class DictDownloader(QThread):
    """Download a hunspell dictionary in a background thread."""

    progress = Signal(str)        # status message
    finished = Signal(bool, str)  # ok, error_msg
    dict_ready = Signal(str)      # hunspell lang code

    def __init__(
        self,
        lang_code: str,
        hunspell_code: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._lang_code = lang_code
        self._code = hunspell_code

    def run(self) -> None:
        self.progress.emit(f"Downloading {self._code}…")
        dest_dir = _dicts_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)

        for ext in ("dic", "aff"):
            url = f"{_GITHUB_BASE}{self._lang_code}/index.{ext}"
            dest = dest_dir / f"{self._code}.{ext}"
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    data = resp.read()
                    dest.write_bytes(data)
                    # Also copy to enchant's hunspell directory
                    _copy_to_enchant_dir(f"{self._code}.{ext}", data)
            except Exception as e:
                self.finished.emit(False, f"Failed {ext}: {e}")
                return

        # Update manifest
        manifest = load_manifest()
        manifest[self._code] = True
        save_manifest(manifest)

        self.finished.emit(True, "")
        self.dict_ready.emit(self._code)


def _get_enchant_hunspell_dir() -> Path | None:
    try:
        import enchant._enchant as _e
        dll = _e.enchant_lib_path
        huns = Path(dll).resolve().parent.parent / "share" / "enchant" / "hunspell"
        if huns.is_dir():
            return huns
    except Exception:
        pass
    return None


def _copy_to_enchant_dir(filename: str, data: bytes) -> None:
    huns = _get_enchant_hunspell_dir()
    if huns is not None:
        try:
            (huns / filename).write_bytes(data)
        except OSError:
            pass


def uninstall_dict(hunspell_code: str) -> bool:
    """Remove dictionary files and update manifest.  Returns True if removed."""
    removed = False
    for dest_dir in (_dicts_dir(), _get_enchant_hunspell_dir()):
        if dest_dir is None:
            continue
        for ext in ("dic", "aff"):
            p = dest_dir / f"{hunspell_code}.{ext}"
            if p.is_file():
                p.unlink()
                removed = True
    manifest = load_manifest()
    manifest.pop(hunspell_code, None)
    save_manifest(manifest)
    return removed


def is_dict_installed(hunspell_code: str) -> bool:
    manifest = load_manifest()
    if manifest.get(hunspell_code):
        dest_dir = _dicts_dir()
        return (dest_dir / f"{hunspell_code}.dic").is_file()
    return False
