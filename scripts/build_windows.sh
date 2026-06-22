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
    --onefile \
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
    --collect-data pygments \
    --hidden-import PySide6.QtSvg \
    main.py

echo "==> ✅  Executable built: dist/$APP.exe"
echo "    Self-contained — distribute this single file."
