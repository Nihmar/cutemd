# CuteMD — Agent Instructions

## Dev commands

```bash
uv run main.py              # run the app
uv sync                     # install/update dependencies
uv run pyinstaller <args>   # use PyInstaller (must be in dev deps)
```

There are **no tests, no linter, and no type checker** configured. Don't run commands that don't exist.

## Package boundaries

- `markdown/` — pure Markdown processing, **no Qt imports**. Used by `ui/`.
- `ui/` — PySide6 GUI layer. Imports from `markdown/` but not the reverse.
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
```

If you add new resource dirs or data packages, update all three build scripts in `scripts/` (`build_windows.bat`, `build_windows.sh`, `build_appimage.sh`).

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

`translations.py` hardcodes `QSettings("cutemd", "cutemd")` (org, app). `main_window.py` likely uses the same or reads `QSettings()` after `setOrganizationName`/`setApplicationName`. Don't change the org/app names without updating both.

## Build quirks

- Windows: `--onedir` produces a folder (faster startup, no temp extraction)
- Linux: `--onedir` + AppDir structure → AppImage
- Both use `--strip --optimize 2 --noupx`
- `--windowed` means no console on Windows
- SVG icons in `ui/icons/` must be included via `--add-data`
