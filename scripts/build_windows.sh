#!/usr/bin/env bash
# Build a standalone Windows .exe of CuteMD.
#
# Prerequisites:
#   uv          – Python package manager
#   PyInstaller – installed via `uv run pip install pyinstaller`
#
# Usage (on Windows in Git Bash or WSL):
#   bash scripts/build_windows.sh
#
set -euo pipefail

APP="cutemd"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Cleaning previous builds …"
rm -rf "$PROJECT_DIR/dist" "$PROJECT_DIR/build" "$PROJECT_DIR/__pycache__"

echo "==> Installing PyInstaller …"
uv pip install pyinstaller

echo "==> Building Windows executable (optimised for speed) …"
cd "$PROJECT_DIR"
uv run pyinstaller \
    --name "$APP" \
    --onedir \
    --windowed \
    --strip \
    --optimize 2 \
    --noupx \
    --noconfirm \
    --add-data "ui/icons;ui/icons" \
    --add-data "ui/style.qss;ui" \
    --add-data "ui/preview_styles.css;ui" \
    --add-data "resources/translations;resources/translations" \
    --add-data "resources/katex;resources/katex" \
    --add-data "resources/cutemd.svg;resources" \
    --add-data "resources/cutemd.ico;resources" \
    --icon resources/cutemd.ico \
    --version-file scripts/file_version_info.txt \
    --collect-data latex2mathml \
    --hidden-import PySide6.QtSvg \
    --hidden-import PySide6.QtPdf \
    --hidden-import PySide6.QtWebEngineWidgets \
    --hidden-import requests \
    main.py

echo "==> ✅  Executable built: dist/$APP/$APP.exe"
echo "    Distribute the entire dist/$APP/ folder."
echo ""
echo "==> Creating installer with Inno Setup …"
ISCC=""
for dir in "/c/Program Files (x86)/Inno Setup 6" "/c/Program Files/Inno Setup 6"; do
    if [ -f "$dir/iscc.exe" ]; then ISCC="$dir/iscc.exe"; break; fi
done
if [ -z "$ISCC" ] && command -v iscc &> /dev/null; then ISCC="iscc"; fi
if [ -n "$ISCC" ]; then
    "$ISCC" scripts/cutemd_setup.iss
    echo "==> ✅  Installer built: dist/CuteMD_Setup.exe"
else
    echo "    Inno Setup not found – install from https://jrsoftware.org/isinfo.php"
    echo "    Expected at: /c/Program Files (x86)/Inno Setup 6/iscc.exe"
fi
