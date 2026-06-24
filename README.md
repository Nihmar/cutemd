# CuteMD

A non-WYSIWYG Markdown editor with live preview, syntax highlighting, folder-based project navigation, and WebDAV cloud sync. Supports both vault-style folder management and single-file edit mode.

![theme](resources/cutemd.svg)

## Features

- **Split editor + live preview** with exact anchor-based scroll sync
- **Folder tree panel** — open a folder, browse `.md` files, single-click to open
- **Tabbed interface** — multiple files open simultaneously, Ctrl+W to close
- **Syntax highlighting** in the editor (headings, bold, italic, code, links…)
- **Code highlighting** in the preview via Pygments
- **Math rendering** — inline `$...$` and block `$$...$$` via LaTeX → MathML
- **Right-click context menus** on the file tree (open in explorer, open with default app, open in new tab) and on the editor (all formatting actions)
- **9 built-in themes** — System, Nord, Gruvbox, Catppuccin Mocha/Latte, Tokyo Night, Dracula, Solarized Dark, Everforest
- **Modern UI** — Fusion style, custom QSS stylesheet, SVG toolbar icons
- **WebDAV sync** — per-folder bidirectional sync via WebDAV (http/https), with mtime-based conflict resolution and local sync state
- **Keyboard shortcuts** for all common actions
- **Persistent state** — last folder, theme choice, window size remembered via QSettings

## Requirements

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) — package manager

## Quick start

```bash
# Clone and enter the project
git clone https://github.com/Nihmar/cutemd.git
cd cutemd

# Install dependencies
uv sync

# Run
uv run main.py
```

## Project structure

```
cutemd/
├── main.py                    # Entry point + __version__
├── ui/                        # Qt / PySide6
│   ├── main_window.py         # MainWindow — tabs, toolbar, menus, dual-mode
│   ├── editor_tab.py          # EditorTab — editor + preview + scroll sync
│   ├── file_tree_panel.py     # FileTreePanel — folder tree widget
│   ├── folder_settings.py     # FolderSettings — per-folder .cutemd/ config
│   ├── syntax_highlighter.py  # MarkdownHighlighter — editor highlighting
│   ├── markdown_completer.py  # MarkdownAutoCompleter — smart editing
│   ├── theme.py               # QSS generation from palette
│   ├── themes.py              # Theme definitions (9 built-in)
│   ├── settings_dialog.py     # Settings dialog (theme, font, shortcuts, storage, WebDAV sync)
│   ├── welcome_dialog.py      # First-launch folder selector
│   ├── webdav_sync.py          # WebDAV client + sync engine with local sync state
│   ├── preview_browser.py      # PreviewTextBrowser + image helpers
│   ├── image_viewer.py        # ImageViewer with zoom/pan
│   ├── pdf_viewer.py          # PdfViewer with fit-width
│   ├── style.qss              # Qt stylesheet template
│   ├── preview_styles.css     # Preview pane CSS
│   └── icons/                 # SVG toolbar icons (16)
├── markdown/                  # Markdown processing (no Qt)
│   ├── html_builder.py        # MD→HTML pipeline, anchors, wikilinks
│   ├── math_renderers.py      # LaTeX → MathML for dollarmath plugin
│   └── tools.py               # Pygments code highlight, heading IDs, anchors
├── resources/                 # Distribution assets
│   ├── cutemd.desktop         # Linux .desktop entry
│   ├── cutemd.svg             # Application icon (SVG)
│   ├── cutemd.ico             # Application icon (Windows)
│   └── translations/          # Qt translation files (.ts / .qm)
├── scripts/                   # Build & utility scripts
│   ├── build_appimage.sh      # Linux AppImage builder
│   ├── build_deb.sh           # Debian / Ubuntu .deb builder
│   ├── build_arch.sh          # Arch Linux package builder
│   ├── PKGBUILD               # Arch Linux PKGBUILD template
│   ├── build_windows.sh       # Windows .exe (Git Bash / WSL)
│   ├── build_windows.bat      # Windows .exe (cmd / PowerShell)
│   ├── cutemd_setup.iss       # Inno Setup installer script
│   ├── file_version_info.txt  # Windows exe version metadata
│   ├── make_ico.py            # Generate .ico from .svg
│   ├── register_windows.ps1   # Windows file association (standalone)
│   └── update_translations.sh # .ts → .qm compilation
├── pyproject.toml
└── uv.lock
```

## Building for distribution

All build scripts produce a self-contained bundle — no Python, Qt, or other runtime dependencies are needed on the target system.

### Linux — AppImage

```bash
# 1. Install PyInstaller
uv pip install pyinstaller

# 2. Download appimagetool (one-time)
wget https://github.com/AppImage/appimagetool/releases/latest/download/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool

# 3. Build the AppImage
./scripts/build_appimage.sh
# → dist/cutemd-x86_64.AppImage

# Optionally install locally (adds to app menu, associates .md files)
./scripts/build_appimage.sh --install
```

The AppImage is self-contained — no dependencies needed on the target system. It registers `text/markdown` MIME type so `.md` files open in CuteMD.

### Linux — Debian / Ubuntu (.deb)

```bash
# Prerequisites: dpkg-deb (included in dpkg, standard on Debian/Ubuntu)
uv pip install pyinstaller

# Build the .deb package
./scripts/build_deb.sh
# → dist/cutemd_<version>_<arch>.deb

# Install
sudo apt install ./dist/cutemd_*.deb
# or: sudo dpkg -i dist/cutemd_*.deb
```

The package installs to `/opt/cutemd/` with a launcher in `/usr/bin/cutemd`, a `.desktop` entry, and the application icon. Desktop MIME databases are refreshed automatically.

To uninstall:
```bash
sudo apt remove cutemd       # remove the package
sudo apt purge cutemd        # also remove config files
```

### Linux — Arch (.pkg.tar.zst)

```bash
# Prerequisites: makepkg, base-devel (standard on Arch), uv
uv pip install pyinstaller

# Build the Arch package
./scripts/build_arch.sh
# → dist/cutemd-<version>-1-<arch>.pkg.tar.zst

# Install
sudo pacman -U ./dist/cutemd-*.pkg.tar.zst
```

The package installs to `/opt/cutemd/` with a launcher in `/usr/bin/cutemd`, a `.desktop` entry, and the application icon.

To uninstall:
```bash
sudo pacman -R cutemd
```

#### Using the PKGBUILD directly

If you prefer to build from source with `makepkg` manually (e.g. for AUR submission or customisation), use the provided `scripts/PKGBUILD` template:

```bash
# 1. Create a build directory and copy source + PKGBUILD
mkdir /tmp/cutemd-build && cd /tmp/cutemd-build
cp -r /path/to/cutemd/{main.py,pyproject.toml,uv.lock,markdown,ui,resources} .

# 2. Substitute the version and run makepkg
sed "s/__VERSION__/$(grep -oP '__version__\s*=\s*"\K[^"]+' /path/to/cutemd/main.py)/" \
    /path/to/cutemd/scripts/PKGBUILD > PKGBUILD

makepkg -si
# -s installs missing dependencies, -i installs the package after building
```

### Windows

```bash
# On Windows (Git Bash, WSL, or PowerShell)
uv pip install pyinstaller
bash scripts/build_windows.sh
# → dist/cutemd/cutemd.exe

# Optional: create installer with Inno Setup
iscc scripts/cutemd_setup.iss
# → dist/CuteMD_Setup.exe
```

Or from a native Windows prompt:

```cmd
REM cmd.exe or PowerShell
uv pip install pyinstaller
scripts\build_windows.bat
REM → dist\cutemd\cutemd.exe
REM → dist\CuteMD_Setup.exe  (if Inno Setup is installed)
```

The Inno Setup installer:
- Installs to `C:\Program Files\CuteMD\`
- Registers `.md` and `.markdown` file associations
- Adds "Open with CuteMD" to the context menu
- Creates Start Menu shortcuts
- Supports upgrades (reinstall over previous version)
- Provides clean uninstall

To register file types without the installer, run:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_windows.ps1 -ExePath "dist\cutemd\cutemd.exe"
```

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+O` | Open folder |
| `Ctrl+N` | New file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | WebDAV Sync Now |
| `Ctrl+W` | Close tab |
| `Ctrl+Q` | Quit |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Ctrl+F` | Find in editor |
| `Ctrl+Shift+F` | Find in files |
| `Ctrl+B` | Toggle file tree |
| `Ctrl+P` | Toggle preview |
| `Ctrl+,` | Settings |
| `Ctrl+/` | Keyboard shortcuts reference |

## Versioning

The version is stored in four places — update all of them in sync:

| File | Key | Applies to |
|---|---|---|
| `pyproject.toml` | `version = "x.y.z"` | Python package metadata (all platforms) |
| `main.py` | `__version__ = "x.y.z"` | Runtime version string (all platforms) |
| `scripts/file_version_info.txt` | `filevers`, `prodvers`, etc. | Windows EXE metadata (via `--version-file`) |
| `scripts/cutemd_setup.iss` | `#define MyAppVersion "x.y.z"` | Inno Setup installer (Windows)

## Themes

Settings → Settings… opens the theme picker. Choose from:

| Theme | Type |
|---|---|
| System | Follows OS light/dark |
| Nord | Dark |
| Gruvbox Dark | Dark |
| Catppuccin Mocha | Dark |
| Catppuccin Latte | Light |
| Tokyo Night | Dark |
| Dracula | Dark |
| Solarized Dark | Dark |
| Everforest | Dark |

## WebDAV Sync

CuteMD can synchronise a folder with any WebDAV server (Nextcloud, OpenMediaVault, Synology, Apache, Nginx…).

**Setup:**
1. Open a folder, then Settings → Sync
2. Enter the WebDAV URL (`https://server.com/dav/notes`), username, and password
3. Click **Test Connection** to verify
4. Save with OK — credentials are saved in `.cutemd/webdav.json`

**Usage:**
- `Ctrl+Shift+S` or File → Sync Now to synchronise
- All files in the folder (excluding `.cutemd/`, `.git/`) are synced
- Sync is bidirectional: new local files are uploaded, new remote files are downloaded
- If a file was modified on both sides, the newest version wins
- A `.cutemd/sync_state.json` keeps track of last-synced timestamps to avoid redundant transfers

## License

MIT
