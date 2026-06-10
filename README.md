# CuteMD

A non-WYSIWYG Markdown editor with live preview, syntax highlighting, and folder-based project navigation — inspired by Obsidian.

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
- **Keyboard shortcuts** for all common actions
- **Persistent state** — last folder, theme choice, window size remembered via QSettings

## Requirements

- Python ≥ 3.14
- [uv](https://docs.astral.sh/uv/) — package manager

## Quick start

```bash
# Clone and enter the project
git clone https://github.com/yourname/cutemd.git
cd cutemd

# Install dependencies
uv sync

# Run
uv run main.py
```

## Project structure

```
cutemd/
├── main.py                    # Entry point
├── ui/                        # Qt / PySide6
│   ├── main_window.py         # MainWindow — tabs, toolbar, menus
│   ├── editor_tab.py          # EditorTab — editor + preview + scroll sync
│   ├── file_tree_panel.py     # FileTreePanel — folder tree widget
│   ├── syntax_highlighter.py  # MarkdownHighlighter — editor highlighting
│   ├── theme.py               # QSS generation from palette
│   ├── themes.py              # Theme definitions (9 built-in)
│   ├── settings_dialog.py     # Settings dialog (theme picker)
│   ├── style.qss              # Qt stylesheet template
│   ├── preview_styles.css     # Preview pane CSS
│   └── icons/                 # SVG toolbar icons (13)
├── markdown/                  # Markdown processing (no Qt)
│   ├── math_renderers.py      # LaTeX → MathML for dollarmath plugin
│   └── tools.py               # Pygments code highlight, heading IDs, anchors
├── resources/                 # Distribution assets
│   ├── cutemd.desktop         # Linux .desktop entry
│   └── cutemd.svg             # Application icon
├── scripts/                   # Build scripts
│   ├── build_appimage.sh      # Linux AppImage builder
│   └── build_windows.sh       # Windows .exe builder
├── pyproject.toml
└── uv.lock
```

## Building for distribution

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

### Windows

```bash
# On Windows (Git Bash, WSL, or PowerShell)
uv pip install pyinstaller
bash scripts/build_windows.sh
# → dist/cutemd.exe
```

The `.exe` is a single self-contained file — no installer needed.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+O` | Open folder |
| `Ctrl+N` | New file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as… |
| `Ctrl+W` | Close tab |
| `Ctrl+Q` | Quit |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |

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

## License

MIT
