# CuteMD

A non-WYSIWYG Markdown editor with live preview, syntax highlighting, folder-based project navigation, and WebDAV cloud sync. Supports both vault-style folder management and single-file edit mode.

![theme](resources/cutemd.svg)

> **Disclaimer:** This project is vibecoded. Although it has been tested and works for my use cases, it may contain bugs, edge cases, or unexpected behavior. **I am not responsible for any loss of data or other damages that may occur from using this software.** Use at your own risk and keep backups of your files.

## Installation

### Pre-built packages (no dependencies required)

Pre-built binaries for Linux (AppImage, .deb, .rpm, Arch) and Windows (.exe, installer) are available on the [releases page](https://github.com/Nihmar/cutemd/releases). These are self-contained — no Python, Qt, or other runtime dependencies needed.

### From source

Requirements:
- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) — package manager

Optional:
- [pandoc](https://pandoc.org) — used for exporting notes to HTML, PDF, ODT, and DOCX

```bash
git clone https://github.com/Nihmar/cutemd.git
cd cutemd
uv sync
uv run main.py
```

## Features

### Editor

- **Live preview** — synchronized split-pane editor + preview with anchor-based scroll sync
- **Syntax highlighting** — headings, bold, italic, strikethrough, inline code, fenced code blocks, math (`$...$` and `$$...$$`), links (`[text](url)`), wikilinks (`[[target]]`), footnotes (`[^label]`), YAML frontmatter, lists, blockquotes
- **Code fence language picker** — Ctrl+Space after ```` ``` ```` opens a filterable popup with 35+ languages (python, rust, javascript, bash, sql, yaml, pascal…)
- **Smart editing** — auto-pair delimiters (`**`, `_`, `~`, `` ` ``), auto-pair brackets, list/blockquote continuation on Enter, backspace unwraps empty pairs
- **Tag autocomplete** — Ctrl+Space after `#` shows known vault tags
- **File autocomplete** — Ctrl+Space inside `](...)` or `[[...]]` shows vault files
- **HTML tag autocomplete** — Ctrl+Space after `<` shows HTML5 tags; closing `>` auto-completes pairs
- **Line numbers** — configurable display modes in Settings

### Navigation

- **Folder tree panel** — open a folder, browse markdown files, single-click to open, Ctrl+B to toggle
- **Tabbed interface** — multiple files open simultaneously, Ctrl+W to close, Ctrl+N for new file
- **Command palette** — Ctrl+P opens a searchable command picker
- **Backlinks panel** — shows files that link to the current note ([[wikilinks]])
- **Tags panel** — aggregates all `#tags` across the vault, group by tag
- **Table of contents** — auto-generated from headings, click to scroll
- **Search in files** — Ctrl+Shift+F searches all markdown files in the vault; Ctrl+Shift+H for replace
- **Daily notes** — Ctrl+Shift+D opens or creates today's note
- **New from template** — Ctrl+Shift+N creates a file from a template
- **Zen mode** — F11 toggles full-screen distraction-free editing

### Tables

- **Tab/Shift+Tab navigation** between cells when cursor is inside a markdown table
- **Tab at last cell** appends a new row automatically
- **Right-click context menu** in a table — Edit Table (QTableWidget popup), Add Row, Add Column
- **Edit Table popup** — add/remove rows and columns with live preview, serializes back to pipe-table markdown on OK
- **Insert Table** — Edit menu or toolbar button opens a dialog to choose rows × columns, inserts the skeleton at cursor position

### Spell checking

- **Hunspell dictionaries** via pyenchant — download language packs from Settings (en, de, es, fr, it, nl, pt)
- **Per-folder custom dictionary** — right-click a misspelled word and choose "Add to dictionary"; saved to `.cutemd/custom_dict.txt`
- **Skip regions** — code blocks, URLs, wikilinks, HTML tags, YAML frontmatter, and `#tags` are excluded from spell checking

### Export

- **File > Export as** submenu — HTML, PDF, ODT, DOCX
- **pandoc** backend — requires `pandoc` installed on the system
- **HTML export** embeds the current preview CSS for theme-matching self-contained output
- **PDF** uses xelatex engine
- **ODT** — native LibreOffice/OpenDocument format
- **DOCX** — Microsoft Word format

### Themes

9 built-in themes, selectable from Settings:

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

### WebDAV Sync

CuteMD can synchronise a folder with any WebDAV server (Nextcloud, OpenMediaVault, Synology, Apache, Nginx…).

**Setup:**
1. Open a folder, then Settings → Sync
2. Enter the WebDAV URL (`https://server.com/dav/notes`), username, and password
3. Click **Test Connection** to verify
4. Save with OK — credentials are saved in `.cutemd/webdav.json`

**Usage:**
- `Ctrl+Alt+S` or File → Sync Now to synchronise
- All files in the folder (excluding `.cutemd/`, `.git/`) are synced
- Sync is bidirectional: new local files are uploaded, new remote files are downloaded
- If a file was modified on both sides, the newest version wins
- A `.cutemd/sync_state.json` keeps track of last-synced timestamps to avoid redundant transfers

### Other

- **9 right-click context menus** — editor formatting (bold, italic, lists, blockquote, links, images, tables, spell-check), file tree (rename, duplicate, delete, copy location, open externally)
- **Modern UI** — Fusion style, custom QSS stylesheet, SVG toolbar icons (16 actions)
- **Internationalization** — UI translated in 6 languages (de, es, fr, it, nl, pt)
- **Persistent state** — last folder, theme, window size, open tabs remembered via QSettings
- **Drag & drop** — drop images from file explorer to insert Markdown image syntax
- **Image viewer** — embedded viewer with zoom and pan for `.png`, `.jpg`, `.gif`, `.webp`, `.svg`
- **PDF viewer** — embedded viewer with fit-to-width for `.pdf` files
- **Link preview** — hover over links and wikilinks to see a popup preview
- **Broken link markers** — links to non-existent files are highlighted in the editor
- **Auto-save** — configurable interval in Settings
- **Session restore** — reopens tabs from last session on startup
- **Line-ending detection** — auto-detects and preserves LF/CRLF
- **Encoding detection** — auto-detects file encoding via chardet

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+O` | Open folder |
| `Ctrl+Shift+O` | Close folder |
| `Ctrl+N` | New file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+Alt+S` | WebDAV Sync Now |
| `Ctrl+W` | Close tab |
| `Ctrl+Q` | Quit |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Ctrl+F` | Find in editor |
| `Ctrl+Shift+F` | Find in files |
| `Ctrl+Shift+H` | Replace in files |
| `Ctrl+B` | Toggle file tree |
| `Ctrl+P` | Toggle preview |
| `Ctrl+Shift+P` | Toggle split |
| `Ctrl+Shift+B` | Toggle status bar |
| `Ctrl+,` | Settings |
| `Ctrl+/` | Keyboard shortcuts reference |
| `Ctrl+=` | Zoom in (editor) |
| `Ctrl+-` | Zoom out (editor) |
| `Ctrl+0` | Reset zoom |
| `Ctrl+Shift+=` | Zoom in (preview) |
| `Ctrl+Shift+-` | Zoom out (preview) |
| `Ctrl+P` | Command palette |
| `Ctrl+Shift+N` | New from template |
| `Ctrl+Shift+D` | Open daily note |
| `F11` | Toggle Zen mode |
| `Ctrl+Shift+Y` | WebDAV Sync Now |

## How to develop

### Project structure

```
cutemd/
├── main.py                    # Entry point + __version__
├── ui/                        # Qt / PySide6
│   ├── main_window.py         # MainWindow — tabs, toolbar, menus, dual-mode
│   ├── editor_tab.py          # EditorTab — editor + preview + scroll sync
│   ├── file_tree_panel.py     # FileTreePanel — folder tree widget
│   ├── folder_settings.py     # FolderSettings — per-folder .cutemd/ config
│   ├── syntax_highlighter.py  # MarkdownHighlighter — editor highlighting
│   ├── table_editor.py        # TableEditor — popup editor, nav, insert dialog
│   ├── dict_manager.py        # DictManager — hunspell dictionary download
│   ├── action_registry.py     # ActionRegistry — QAction + menu bar factory
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
├── core/                      # Backend logic (no Qt)
│   ├── exporter.py            # Export to HTML/PDF/ODT/DOCX via pandoc
│   ├── spell_checker.py       # Spell checker — pyenchant + custom dict
│   └── ...
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

### Dev commands

```bash
uv run main.py              # run the app
uv sync                     # install/update dependencies
uv run pyinstaller <args>   # use PyInstaller (must be in dev deps)
```

There are **no tests, no linter, no type checker** configured.

### Building for distribution

All build scripts produce a self-contained bundle — no Python, Qt, or other runtime dependencies are needed on the target system.

#### Linux — AppImage

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

#### Linux — Debian / Ubuntu (.deb)

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

#### Linux — Arch (.pkg.tar.zst)

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

##### Using the PKGBUILD directly

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

#### Windows

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

### Versioning

The version is stored in four places — update all of them in sync:

| File | Key | Applies to |
|---|---|---|
| `pyproject.toml` | `version = "1.0.0"` | Python package metadata (all platforms) |
| `main.py` | `__version__ = "1.0.0"` | Runtime version string (all platforms) |
| `scripts/file_version_info.txt` | `filevers`, `prodvers`, etc. | Windows EXE metadata (via `--version-file`) |
| `scripts/cutemd_setup.iss` | `#define MyAppVersion "x.y.z"` | Inno Setup installer (Windows)

## Known limitations

- **Footnotes:** Editor syntax highlighting for `[^label]` references and `[^label]:` definitions is supported. Preview rendering (numbered superscripts, bidirectional links, definitions collected at bottom) is under active development and may not be fully functional yet.

## License

MIT
