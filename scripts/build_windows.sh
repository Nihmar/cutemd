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
    --add-data "resources/cutemd.svg;resources" \
    --collect-data latex2mathml \
    --hidden-import PySide6.QtSvg \
    --hidden-import PySide6.QtPdf \
    main.py

echo "==> ✅  Executable built: dist/$APP/$APP.exe"
echo "    Distribute the entire dist/$APP/ folder."
echo ""
echo "==> Creating installer with Inno Setup …"
if command -v iscc &> /dev/null; then
    iscc scripts/cutemd_setup.iss
    echo "==> ✅  Installer built: dist/CuteMD_Setup.exe"
else
    echo "    Inno Setup not found on PATH – skipping installer."
    echo "    Install from https://jrsoftware.org/isinfo.php and run:"
    echo "      iscc scripts/cutemd_setup.iss"
fi
