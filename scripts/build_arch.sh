#!/usr/bin/env bash
# Build an Arch Linux package (.pkg.tar.zst) of CuteMD.
#
# Prerequisites:
#   uv          – Python package manager (https://docs.astral.sh/uv)
#   makepkg     – included in pacman (standard on Arch Linux)
#   base-devel  – for fakeroot, strip, etc.
#
# Usage:
#   ./scripts/build_arch.sh
#   # → dist/cutemd-<version>-1-<arch>.pkg.tar.zst
#
#   sudo pacman -U ./dist/cutemd-*.pkg.tar.zst
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

# Verify tools are available
if ! command -v makepkg &>/dev/null; then
    echo "ERROR: makepkg not found. Install pacman and base-devel."
    echo "       This script must be run on Arch Linux or an Arch-based distro."
    exit 1
fi

if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install it from https://docs.astral.sh/uv/"
    exit 1
fi

# ── clean ────────────────────────────────────────────────────────────

echo "==> Cleaning previous builds …"
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/__pycache__"

# ── prepare build directory ──────────────────────────────────────────

BUILDDIR="$BUILD_DIR/archpkg"
rm -rf "$BUILDDIR"
mkdir -p "$BUILDDIR"

echo "==> Preparing PKGBUILD …"

# Substitute version into the PKGBUILD template
sed "s/__VERSION__/$VERSION/g" "$SCRIPT_DIR/PKGBUILD" > "$BUILDDIR/PKGBUILD"

# The PKGBUILD uses $startdir as the project root.  We arrange things so
# that $startdir (the directory containing the PKGBUILD) is the source
# root.  We create a symlink farm pointing back to the project files.
# This avoids duplicating the entire source tree and lets makepkg work
# with the real project directory (excluding dist/, build/, .venv/).

echo "==> Linking project files into build directory …"
shopt -s dotglob
for item in "$PROJECT_DIR"/*; do
    name="$(basename "$item")"
    # Skip directories we don't need in the build environment
    case "$name" in
        .venv|.git|dist|build|__pycache__|*.egg-info) continue ;;
    esac
    ln -sf "$item" "$BUILDDIR/$name"
done
shopt -u dotglob

# ── build ────────────────────────────────────────────────────────────

echo "==> Building Arch package with makepkg …"
cd "$BUILDDIR"

# makepkg options:
#   -s  : install missing dependencies with pacman
#   -f  : force rebuild (overwrite existing package)
#   --skipinteg : skip checksum verification (we build from local source)
makepkg -sf --skipinteg

# ── collect output ───────────────────────────────────────────────────

echo "==> Collecting package …"
mkdir -p "$DIST_DIR"
mv "$BUILDDIR/$APP"-*.pkg.tar.zst "$DIST_DIR/" 2>/dev/null || true

echo ""
echo "==> ✅  Arch package built: dist/$APP-$VERSION-1-*.pkg.tar.zst"
echo "    Install with:  sudo pacman -U dist/$APP-$VERSION-1-*.pkg.tar.zst"

# ── cleanup build directory ──────────────────────────────────────────

rm -rf "$BUILDDIR"
