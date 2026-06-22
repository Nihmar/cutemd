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
--collect-data latex2mathml
--collect-data pygments
--hidden-import PySide6.QtSvg
```

If you add new resource dirs or data packages, update both build scripts in `scripts/`.

## Theme / QSS system

- `ui/theme.py` reads `style.qss` and replaces `${KEY}` placeholders with `QPalette` colors at runtime.
- `ui/themes.py` defines the 9 color palettes.
- `ui/preview_styles.css` is plain CSS injected into the web preview pane — no `${KEY}` substitution.

## Translations

- Source: `resources/translations/cutemd_<lang>.ts`
- Compiled: `resources/translations/cutemd_<lang>.qm` (`.qm` files are gitignored)
- Update translations: `bash scripts/update_translations.sh` (uses `pyside6-lupdate` / `pyside6-lrelease`). Needs the `.venv` installed.
- `translations.py` loads `.qm` files and sends `LanguageChange` events. Any widget showing translated text must handle `changeEvent` and call `retranslateUi()`.

## QSettings keys

`translations.py` hardcodes `QSettings("cutemd", "cutemd")` (org, app). `main_window.py` likely uses the same or reads `QSettings()` after `setOrganizationName`/`setApplicationName`. Don't change the org/app names without updating both.

## Build quirks

- Windows: `--onefile` produces a single `.exe`
- Linux: `--onedir` + AppDir structure → AppImage
- Both use `--strip --optimize 2 --noupx`
- `--windowed` means no console on Windows
- SVG icons in `ui/icons/` must be included via `--add-data`
