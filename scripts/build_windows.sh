#!/usr/bin/env bash
# Build a standalone Windows .exe of CuteMD (cross-compile from Linux or run on Windows).
#
# Prerequisites:
#   uv          – Python package manager
#   PyInstaller – installed via `uv run pip install pyinstaller`
#
# Usage (on Windows):
#   uv run pip install pyinstaller
#   bash scripts/build_windows.sh
#
# Or cross-compile from Linux (requires wine + windows Python, not recommended).
# Simplest: run this script directly on a Windows machine with Git Bash or WSL.
#
set -euo pipefail

APP="cutemd"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Cleaning previous builds …"
rm -rf "$PROJECT_DIR/dist" "$PROJECT_DIR/build" "$PROJECT_DIR/__pycache__"

echo "==> Installing PyInstaller …"
uv pip install pyinstaller

echo "==> Building Windows executable …"
cd "$PROJECT_DIR"
uv run pyinstaller \
    --name "$APP" \
    --onefile \
    --windowed \
    --add-data "ui/icons;ui/icons" \
    --add-data "ui/style.qss;ui" \
    --add-data "ui/preview_styles.css;ui" \
    --collect-data latex2mathml \
    --collect-data pygments \
    --hidden-import PySide6.QtSvg \
    main.py

echo "==> ✅  Executable built: dist/$APP.exe"
echo "    Distribute dist/$APP.exe as a standalone application."
echo "    No installer needed – it's a single self-contained file."
