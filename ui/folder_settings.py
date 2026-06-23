"""Per-folder settings stored in <folder>/.cutemd/."""

import json
from pathlib import Path


class FolderSettings:
    """Manages settings stored in a ``.cutemd`` directory inside a folder."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder.resolve()
        self._dotdir = self._folder / ".cutemd"
        self._config_path = self._dotdir / "settings.json"
        self._shortcuts_path = self._dotdir / "shortcuts.json"
        self._webdav_path = self._dotdir / "webdav.json"
        self._values: dict = {}

    @property
    def folder(self) -> Path:
        return self._folder

    @property
    def dotdir_path(self) -> Path:
        return self._dotdir

    @property
    def config_path(self) -> Path:
        return self._config_path

    def images_dir(self) -> Path:
        """Return the configured images directory (created on demand).

        Resolved relative to the opened folder, never outside it.
        Defaults to ``"images"`` unless overridden in settings.json.
        """
        name = str(self._values.get("images_dir", "images")).strip()
        if not name or ".." in name or "/" in name or "\\" in name:
            name = "images"
        target = self._folder / name
        target.mkdir(parents=True, exist_ok=True)
        return target

    def load(self) -> dict:
        if self._config_path.is_file():
            try:
                self._values = json.loads(self._config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._values = {}
        else:
            self._values = {}
        return dict(self._values)

    def save(self, data: dict) -> None:
        self._dotdir.mkdir(parents=True, exist_ok=True)
        self._values = dict(data)
        self._config_path.write_text(
            json.dumps(self._values, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load_shortcuts(self) -> dict[str, str]:
        if self._shortcuts_path.is_file():
            try:
                return json.loads(self._shortcuts_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save_shortcuts(self, data: dict[str, str]) -> None:
        self._dotdir.mkdir(parents=True, exist_ok=True)
        self._shortcuts_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def dotdir_size(self) -> int:
        if not self._dotdir.is_dir():
            return 0
        total = 0
        for f in self._dotdir.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        return total

    # -- typed accessors (return None when not overridden) --

    def get_theme(self) -> str | None:
        v = self._values.get("theme")
        return str(v) if isinstance(v, str) and v else None

    def get_editor_font_family(self) -> str | None:
        v = self._values.get("editor_font_family")
        return str(v) if isinstance(v, str) and v else None

    def get_editor_font_size(self) -> int | None:
        v = self._values.get("editor_font_size")
        return int(v) if isinstance(v, (int, float)) and v > 0 else None

    def get_preview_font_family(self) -> str | None:
        v = self._values.get("preview_font_family")
        return str(v) if isinstance(v, str) and v else None

    def get_preview_font_size(self) -> int | None:
        v = self._values.get("preview_font_size")
        return int(v) if isinstance(v, (int, float)) and v > 0 else None

    def load_webdav_config(self) -> dict | None:
        if self._webdav_path.is_file():
            try:
                return json.loads(self._webdav_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def save_webdav_config(self, data: dict) -> None:
        self._dotdir.mkdir(parents=True, exist_ok=True)
        self._webdav_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def clear_webdav_config(self) -> None:
        if self._webdav_path.is_file():
            self._webdav_path.unlink()

    def has_webdav_config(self) -> bool:
        return self._webdav_path.is_file()
