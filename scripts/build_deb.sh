#!/usr/bin/env bash
# Build a .deb package of CuteMD for Debian / Ubuntu.
#
# Prerequisites:
#   uv          – Python package manager (https://docs.astral.sh/uv)
#   dpkg-deb    – included in dpkg (standard on Debian/Ubuntu)
#
# Usage:
#   ./scripts/build_deb.sh
#   # → dist/cutemd_<version>_<arch>.deb
#
#   sudo apt install ./dist/cutemd_*.deb
#
set -euo pipefail

APP="cutemd"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$PROJECT_DIR/dist"
BUILD_DIR="$PROJECT_DIR/build"

# ── helpers ──────────────────────────────────────────────────────────

# Extract version from main.py
VERSION=$(grep -oP '__version__\s*=\s*"\K[^"]+' "$PROJECT_DIR/main.py")
echo "==> Version: $VERSION"

# Map uname -m → Debian architecture
case "$(uname -m)" in
    x86_64)  DEB_ARCH="amd64" ;;
    aarch64) DEB_ARCH="arm64" ;;
    armv7l)  DEB_ARCH="armhf" ;;
    *)       echo "Unknown architecture: $(uname -m)"; exit 1 ;;
esac
echo "==> Architecture: $DEB_ARCH"

PKG_NAME="${APP}_${VERSION}_${DEB_ARCH}"
DEB_DIR="$DIST_DIR/$PKG_NAME"

# ── clean ────────────────────────────────────────────────────────────

echo "==> Cleaning previous builds …"
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/__pycache__"

# ── PyInstaller build ────────────────────────────────────────────────

echo "==> Installing PyInstaller …"
uv pip install pyinstaller

echo "==> Building executable with PyInstaller (optimised for speed) …"
cd "$PROJECT_DIR"
uv run pyinstaller \
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
    --add-data "resources/cutemd.svg:resources" \
    --collect-data latex2mathml \
    --hidden-import PySide6.QtSvg \
    --hidden-import PySide6.QtPdf \
    --hidden-import requests \
    main.py

# ── .deb package structure ───────────────────────────────────────────

echo "==> Creating .deb package structure …"

# Install paths (FHS-compliant)
mkdir -p "$DEB_DIR/opt/$APP"
mkdir -p "$DEB_DIR/usr/bin"
mkdir -p "$DEB_DIR/usr/share/applications"
mkdir -p "$DEB_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$DEB_DIR/DEBIAN"

# Copy the PyInstaller bundle to /opt/cutemd
cp -r "$DIST_DIR/$APP/"* "$DEB_DIR/opt/$APP/"

# Launcher symlink in /usr/bin → /opt/cutemd/cutemd
ln -sf "/opt/$APP/$APP" "$DEB_DIR/usr/bin/$APP"

# Desktop entry
cp "$PROJECT_DIR/resources/$APP.desktop" "$DEB_DIR/usr/share/applications/"

# Icon
cp "$PROJECT_DIR/resources/$APP.svg" "$DEB_DIR/usr/share/icons/hicolor/scalable/apps/"

# ── DEBIAN/control ───────────────────────────────────────────────────

# Compute installed size (in KiB, as required by Debian policy)
INSTALLED_SIZE=$(du -sk "$DEB_DIR" | cut -f1)

cat > "$DEB_DIR/DEBIAN/control" << EOF
Package: $APP
Version: $VERSION
Architecture: $DEB_ARCH
Maintainer: Alessandro Nihmar <alessandro@nihmar.com>
Installed-Size: $INSTALLED_SIZE
Section: editors
Priority: optional
Homepage: https://github.com/Nihmar/cutemd
Depends: libc6 (>= 2.28)
Description: A non-WYSIWYG Markdown editor with live preview
 CuteMD is a Markdown editor featuring split editor/preview,
 syntax highlighting, folder-based project navigation,
 WebDAV cloud sync, and 9 built-in themes.
 It supports both vault-style folder management and single-file edit mode.
EOF

# ── DEBIAN/postinst ──────────────────────────────────────────────────

cat > "$DEB_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e
# Update the desktop MIME database after installation
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache /usr/share/icons/hicolor || true
fi
EOF
chmod 755 "$DEB_DIR/DEBIAN/postinst"

# ── DEBIAN/postrm ────────────────────────────────────────────────────

cat > "$DEB_DIR/DEBIAN/postrm" << 'EOF'
#!/bin/sh
set -e
# Clean up desktop database after removal
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database /usr/share/applications || true
    fi
fi
EOF
chmod 755 "$DEB_DIR/DEBIAN/postrm"

# ── build the .deb ───────────────────────────────────────────────────

echo "==> Building .deb package …"
dpkg-deb --build "$DEB_DIR" "$DIST_DIR/${PKG_NAME}.deb"

echo ""
echo "==> ✅  .deb package built: dist/${PKG_NAME}.deb"
echo "    Install with:  sudo apt install ./dist/${PKG_NAME}.deb"
echo "    Or:            sudo dpkg -i dist/${PKG_NAME}.deb"
