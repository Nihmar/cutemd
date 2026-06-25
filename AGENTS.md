# CuteMD — Agent Instructions

## Dev commands

```bash
uv run main.py              # run the app
uv sync                     # install/update dependencies
uv run pyinstaller <args>   # use PyInstaller (must be in dev deps)
```

There are **no tests, no linter, no type checker, and no CI** configured. Don't run commands that don't exist.

## Package boundaries

- `markdown/` — pure Markdown processing, **no Qt imports**. Used by `ui/`.
- `core/` — shared infrastructure (logging). No Qt imports. Importable by all packages.
- `ui/` — PySide6 GUI layer. Imports from `markdown/` and `core/` but not the reverse.
- `ui/webdav_sync.py` — WebDAV client (`WebDAVClient`) + sync engine (`sync_folder`). Exposes `WebDAVConfig`, `SyncResult`. Uses `requests` for HTTP, parses PROPFIND responses with `xml.etree.ElementTree`. Sync algorithm uses Depth-1 PROPFIND with manual BFS recursion (most servers block Depth infinity). Maintains `.cutemd/sync_state.json` to track last-synced timestamps and avoid redundant transfers.
- `main.py` — entry point. Creates `QApplication`, sets app/org name, loads translations, applies theme, shows `MainWindow`.
- `markdown/tools.py` exposes `set_pygments_style(name)` — call this from the UI layer when the theme changes, never import `ui.themes` from `markdown/`.

## Resource paths (PyInstaller-aware)

Always use `_resolve_path()` from `ui/theme.py` (or equivalent `getattr(sys, "frozen", False)` check) when loading files at runtime. PyInstaller bundles freeze to `sys._MEIPASS`. The build scripts show which data is included:

```
--add-data "ui/icons;ui/icons"
--add-data "ui/style.qss;ui"
--add-data "ui/preview_styles.css;ui"
--add-data "resources/translations;resources/translations"
--add-data "resources/cutemd.svg;resources"
--add-data "resources/cutemd.ico;resources"
--icon resources/cutemd.ico
--version-file scripts/file_version_info.txt
--collect-data latex2mathml
--hidden-import PySide6.QtSvg
--hidden-import PySide6.QtPdf
--hidden-import requests
```

If you add new resource dirs or data packages, update all three build scripts in `scripts/` (`build_windows.bat`, `build_windows.sh`, `build_appimage.sh`).

## Debug logging convention

Always use the shared logger from `core/logging.py`:

```python
from core.logging import setup_logging

_LOG = setup_logging("cutemd.{module}")
```

Use `_LOG.debug(...)` for all debug output (never `print`). This way:

- **Terminal** (`uv run main.py`): output goes to stderr, visible in the terminal
- **GUI** (double-click `.exe`, AppImage, desktop launcher): ``NullHandler`` discards all output silently
- **No files** are written to disk — no more `cutemd_*_debug.log` clutter
- The setup is **module-level**: logger configured once at import time

The detection logic uses ``sys.stderr.isatty()`` (all platforms) with an additional
``GetConsoleWindow()`` check on Windows frozen builds to correctly detect GUI mode.

### Windows installers

- **Inno Setup**: `scripts/cutemd_setup.iss` — creates `CuteMD_Setup.exe`. Prerequisites: Inno Setup 6+.
- **Standalone registration**: `scripts/register_windows.ps1` — registers `.md` file association without an installer. Run as admin.
- **Icon generation**: `scripts/make_ico.py` — generates `resources/cutemd.ico` from the SVG. Run with `uv run`.

## Theme / QSS system

- `ui/theme.py` reads `style.qss` and replaces `${KEY}` placeholders with `QPalette` colors at runtime.
- `ui/themes.py` defines the 9 color palettes.
- `ui/preview_styles.css` is plain CSS injected into the web preview pane — no `${KEY}` substitution.

## Versioning

The version is stored in four locations — **update all of them in sync** when bumping:

| File | Field(s) | Platform |
|---|---|---|
| `pyproject.toml` | `version = "x.y.z"` | All |
| `main.py` | `__version__ = "x.y.z"` | All |
| `scripts/file_version_info.txt` | `filevers`, `prodvers`, `FileVersion`, `ProductVersion` | Windows EXE metadata |
| `scripts/cutemd_setup.iss` | `#define MyAppVersion "x.y.z"` | Windows Inno Setup installer |

The `--version-file` flag in the Windows build scripts embeds metadata into `cutemd.exe` (visible in File Properties → Details).

On Linux/AppImage, version is read from `pyproject.toml` / `main.py.__version__` at build time.

## Translations

- Source: `resources/translations/cutemd_<lang>.ts`
- Compiled: `resources/translations/cutemd_<lang>.qm` (`.qm` files are gitignored)
- Update translations: `bash scripts/update_translations.sh` (uses `pyside6-lupdate` / `pyside6-lrelease`). Needs the `.venv` installed.
- `translations.py` loads `.qm` files and sends `LanguageChange` events. Any widget showing translated text must handle `changeEvent` and call `retranslateUi()`.

## QSettings keys

`translations.py` hardcodes `QSettings("cutemd", "cutemd")` (org, app). `main_window.py` uses the same. Don't change the org/app names without updating both.

## UI completeness rule

Every setting stored to QSettings (or any other config store) **must** have a visible UI control to let the user view and change it. Every keyboard shortcut **must** be listed in a menu, have an icon-label tooltip, or appear in the Shortcuts editor. Never leave a setting or shortcut accessible only via raw config editing — add the corresponding UI widget, menu action, or shortcut-table entry in the same commit.

Similarly, when adding a new action (even without a QSetting), always add a menu entry so the user can discover it.

## WebDAV sync notes

- Credentials are stored **plaintext** in `.cutemd/webdav.json` as `{"url", "username", "password"}`.
- The sync engine stores a local state in `.cutemd/sync_state.json` — `{relpath: mtime}`. This enables detecting which files were modified locally or remotely since the last sync.
- `Depth: infinity` is avoided because many servers (nginx, OpenMediaVault) reject it with 403. Instead, Depth-1 PROPFIND is used recursively (BFS).
- Href paths from the server are resolved relative to the first `is_dir` entry in each PROPFIND response, not relative to the configured URL — this handles reverse-proxy path rewrites correctly.
- Downloaded files get their `mtime` set via `os.utime()` to match the server's `getlastmodified`.

## Build quirks

- Windows: `--onedir` produces a folder (faster startup, no temp extraction)
- Linux: `--onedir` + AppDir structure → AppImage
- Both use `--strip --optimize 2 --noupx`
- `--windowed` means no console on Windows
- SVG icons in `ui/icons/` must be included via `--add-data`

## Link preview popup

- `ui/link_preview_popup.py` — `LinkPreviewPopup(QFrame)` shown on hover over Markdown/wikilinks.
- `ui/editor_tab.py` owns the popup: creates it in `__init__`, manages a 400ms `_link_preview_show_timer` in `_on_mouse_move`.
- **Link detection**: `_LINK_RE` (`[text](url)`) and `_WIKILINK_RE` (`!?[[target]]` — optional `!` for embeds).
- **Path resolution** (`EditorTab._resolve_link_target`) in order:
  1. Absolute paths (if they exist).
  2. Relative to the current file's directory (exact name, then + `.md`/`.markdown`).
  3. The folder-settings images directory (`_images_dir`) by filename only.
  4. **Extension fallback**: if the target has no image/PDF extension, try all `_IMG_EXTS` + `_PDF_EXTS` in the base and images dir.
  5. **Tree walk**: walk up to 5 ancestor directories, checking for the file directly and in immediate subdirectories (handles Obsidian-style vaults where images live in `attachments/`, `assets/`, etc. anywhere in the tree).
- **Image resolution does NOT depend on the `.cutemd` images folder setting** — that is only one step in the chain. The tree-walk fallback finds images regardless.
- The popup uses `Qt.WindowType.Tool | FramelessWindowHint | WindowStaysOnTopHint`; `WA_ShowWithoutActivating` avoids focus stealing.
- Supported preview types: text (editor with syntax highlight for `.md`), images (scaled `QPixmap`), PDF (first page via `QPdfDocument`).
