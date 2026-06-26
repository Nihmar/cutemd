# CuteMD — Agent Instructions

## Dev commands

```bash
uv run main.py              # run the app
uv sync                     # install/update dependencies
uv run pyinstaller <args>   # use PyInstaller (must be in dev deps)
uv run scripts/make_ico.py  # regenerate resources/cutemd.ico from SVG
```

No tests, linter, or type checker configured. Don't run commands that don't exist.

CI: `.github/workflows/release.yml` — auto-builds AppImage + Windows .exe/installer on `git tag v*`.

## Committing

Never commit without asking. Include `Fixes #<number>` in the commit message body for GitHub auto-close.

## Package boundaries

| Package | Qt imports? | Inbound from |
|---|---|---|
| `markdown/` | ❌ No | `ui/` only |
| `core/` | ❌ No | `ui/`, `markdown/` |
| `ui/` | ✅ Yes | (none import this) |

- `markdown/tools.py` exposes `set_pygments_style(name)` — call from UI layer on theme change, never `ui.<anything>` from `markdown/`.
- `core/updater.py` — pure update-checking logic (`check_for_update()`, `download_release()`). Uses `requests`.
- `core/services/` — `link_resolver.py`, `anchor_map.py`, `file_io.py`, `folder_setup.py`, `recent_folders.py`.
- `main.py` — entry point; `__version__` is source of truth (read via `__import__("main").__version__` everywhere else).

## Key UI components

- `ui/widgets.py` — `CuteListWidget(QListWidget)` with `setSpacing(6)`. Used by command palette, search, settings, TOC, welcome dialog.
- `ui/command_palette.py` — `CommandPalette(QDialog)`, activated by `act_command_palette` (Ctrl+P). Popup-style (`FramelessWindowHint`).
- `ui/update_dialog.py` — `UpdateAvailableDialog`, `_DownloadThread`. Shows release notes, offers download + launch.
- `ui/link_preview_popup.py` — `LinkPreviewPopup(QFrame)` hover popup for Markdown/wikilinks. 400ms timer in `EditorTab._on_mouse_move`.

## Copy-code button

`markdown/html_builder.py:_inject_copy_buttons()` injects `<a href="http://cutemd-copy/BASE64">` before each `<pre><code>`. `ui/preview_browser.py:_on_anchor_clicked()` intercepts `http://cutemd-copy/` → `base64.urlsafe_b64decode` → `clipboard.setText()`. Set `setOpenLinks(False)` on the browser.

## Missing file creation on link/wikilink click

`ui/editor_tab.py:file_link_clicked` emits `Signal(str, str)` → `main_window.py:_on_file_link_clicked()` creates a new `.md` file (with heading if display text starts with `#`) when the target doesn't exist and a folder is open.

## Menu bar visibility

Toggle in Settings > General > INTERFACE. When hidden, a fallback `QShortcut("Ctrl+P")` is installed (Windows disables QAction shortcuts without a visible menu bar). All actions use `ApplicationShortcut` context via `ShortcutManager.apply()` so they work regardless.

`act_toggle_split` is deprecated — hidden from menu, action preserved for backward compat, no default shortcut.

## Resource paths (PyInstaller-aware)

Use `_resolve_path()` from `ui/theme.py` (or equivalent `getattr(sys, "frozen", False)` check). Bundled data:

```
--add-data "ui/icons;ui/icons"
--add-data "ui/style.qss;ui"
--add-data "ui/preview_styles.css;ui"
--add-data "resources/translations;resources/translations"
--add-data "resources/cutemd.svg;resources"
--add-data "resources/cutemd.ico;resources"
--collect-data latex2mathml
--hidden-import PySide6.QtSvg  PySide6.QtPdf  requests
```

If adding resource dirs, update all three build scripts (`scripts/build_windows.bat`, `scripts/build_windows.sh`, `scripts/build_appimage.sh`).

## Debug logging

```python
from core.logging import setup_logging
_LOG = setup_logging("cutemd.{module}")
```

Use `_LOG.debug(...)` everywhere (never `print`). Terminal → stderr; GUI → `NullHandler`; no files written to disk.

## Versioning — update ALL four in sync

| File | Field |
|---|---|
| `pyproject.toml` | `version = "x.y.z"` |
| `main.py` | `__version__` |
| `scripts/file_version_info.txt` | `filevers`, `prodvers` |
| `scripts/cutemd_setup.iss` | `#define MyAppVersion` |

## QSettings

Always `QSettings("cutemd", "cutemd")` (org, app). Don't change without updating both `main_window.py` and `translations.py`.

## UI completeness rule

Every setting stored to QSettings must have a visible UI control. Every shortcut must appear in a menu, tooltip, or Shortcuts editor. Never leave a setting or shortcut accessible only via raw config editing.

## Theme / QSS

- `ui/theme.py` reads `style.qss`, replaces `${KEY}` with `QPalette` colors.
- `ui/themes.py` defines 9 palettes.
- `ui/preview_styles.css` — plain CSS, no `${KEY}` substitution.

## Link preview

- `_LINK_RE` (`[text](url)`) and `_WIKILINK_RE` (`!?[[target]]`) in `EditorTab`.
- Path resolution (`EditorTab._resolve_link_target`):
  1. Absolute paths
  2. Relative to current file (exact, then + `.md`/`.markdown`)
  3. Attachments dir (`.cutemd` setting)
  4. Extension fallback: try `_IMG_EXTS` + `_PDF_EXTS`
  5. Tree walk: up to 5 ancestor dirs + immediate subdirs
- Popup: `Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint`, `WA_ShowWithoutActivating`.

## WebDAV

- Credentials: plaintext `.cutemd/webdav.json` as `{url, username, password}`.
- State: `.cutemd/sync_state.json` — `{relpath: mtime}`.
- Depth-1 PROPFIND + manual BFS (servers reject Depth infinity).
- Downloaded files get `os.utime()` from `getlastmodified`.
- Href resolution: relative to first `is_dir` in each PROPFIND response (handles reverse-proxy rewrites).

## Build quirks

- Windows: `--onedir` (faster startup), `--windowed` (no console).
- Linux: `--onedir` + AppDir → AppImage.
- Both: `--strip --optimize 2 --noupx`.
- SVG icons in `ui/icons/` must be `--add-data`.
