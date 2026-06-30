#!/usr/bin/env bash
# Build a self-contained AppImage of CuteMD for Linux.
#
# Prerequisites:
#   uv          – Python package manager (https://docs.astral.sh/uv)
#   PyInstaller – installed via `uv run pip install pyinstaller`
#   appimagetool – https://github.com/AppImage/appimagetool/releases
#
# Usage:
#   ./scripts/build_appimage.sh           # builds AppImage
#   ./scripts/build_appimage.sh --install  # also installs .desktop + icon locally
#
set -euo pipefail

APP="cutemd"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$PROJECT_DIR/dist"
BUILD_DIR="$PROJECT_DIR/build"
APPDIR="$DIST_DIR/$APP.AppDir"

INSTALL_LOCAL=false
if [[ "${1:-}" == "--install" ]]; then
    INSTALL_LOCAL=true
fi

echo "==> Cleaning previous builds …"
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/__pycache__"

echo "==> Installing PyInstaller …"
uv python pin 3.13
uv run python -m pip install pyinstaller

echo "==> Building executable with PyInstaller (optimised for speed) …"
cd "$PROJECT_DIR"
uv run python -m PyInstaller \
    --name "$APP" \
    --onedir \
    --windowed \
    --strip \
    --optimize 2 \
    --noupx \
    --noconfirm \
    --add-data "ui/icons:ui/icons" \
    --add-data "ui/style.qss:ui" \
    --add-data "ui/preview_styles.css:ui" \
    --add-data "resources/translations:resources/translations" \
    --add-data "resources/katex:resources/katex" \
    --add-data "resources/cutemd.svg:resources" \
    --collect-data latex2mathml \
    --hidden-import PySide6.QtSvg \
    --hidden-import PySide6.QtPdf \
    --hidden-import PySide6.QtWebEngineWidgets \
    --hidden-import requests \
    main.py

echo "==> Creating AppDir structure …"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

# --onedir produces a directory: dist/cutemd/
cp -r "$DIST_DIR/$APP/"* "$APPDIR/usr/bin/"

cp "$PROJECT_DIR/resources/$APP.desktop" "$APPDIR/usr/share/applications/"
cp "$PROJECT_DIR/resources/$APP.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"

# AppRun launcher
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/bin/cutemd" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# Symlinks for AppImage tool
ln -sf usr/share/applications/cutemd.desktop "$APPDIR/cutemd.desktop"
ln -sf usr/share/icons/hicolor/scalable/apps/cutemd.svg "$APPDIR/cutemd.svg"
ln -sf usr/share/icons/hicolor/scalable/apps/cutemd.svg "$APPDIR/.DirIcon"

# Try appimagetool in several locations
APPIMAGETOOL=""
for candidate in appimagetool appimagetool-x86_64.AppImage "$PROJECT_DIR/appimagetool"; do
    if command -v "$candidate" &>/dev/null || [ -x "$candidate" ]; then
        APPIMAGETOOL="$candidate"
        break
    fi
done

if [ -z "$APPIMAGETOOL" ]; then
    echo "==> ⚠  appimagetool not found."
    echo "    Download it from: https://github.com/AppImage/appimagetool/releases"
    echo "    Place the AppImage in your PATH or in $PROJECT_DIR/"
    echo "    AppDir is ready at: $APPDIR"
    exit 1
fi

echo "==> Packaging AppImage …"
ARCH=$(uname -m)
"$APPIMAGETOOL" "$APPDIR" "$DIST_DIR/$APP-$ARCH.AppImage"

echo "==> ✅  AppImage built: $DIST_DIR/$APP-$ARCH.AppImage"

# Optional local install
if $INSTALL_LOCAL; then
    echo "==> Installing locally …"
    mkdir -p "$HOME/.local/bin"
    mkdir -p "$HOME/.local/share/applications"
    mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"

    cp "$DIST_DIR/$APP-$ARCH.AppImage" "$HOME/.local/bin/$APP"
    cp "$PROJECT_DIR/resources/$APP.desktop" "$HOME/.local/share/applications/"
    cp "$PROJECT_DIR/resources/$APP.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/"

    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    echo "==> ✅  Installed to ~/.local/"
fi
