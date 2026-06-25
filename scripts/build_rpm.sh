#!/usr/bin/env bash
# Build an RPM package of CuteMD for Fedora / RHEL / CentOS.
#
# Prerequisites:
#   rpm-build – installed via `dnf install rpm-build` or `apt install rpm`
#
# Usage:
#   ./scripts/build_rpm.sh
#   # → dist/cutemd-<version>-1.<arch>.rpm
#
#   sudo dnf install ./dist/cutemd-*.rpm
#
set -euo pipefail

APP="cutemd"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$PROJECT_DIR/dist"

VERSION=$(grep -oP '__version__\s*=\s*"\K[^"]+' "$PROJECT_DIR/main.py")
echo "==> Version: $VERSION"

echo "==> Cleaning previous builds …"
rm -rf "$DIST_DIR" "$PROJECT_DIR/build" "$PROJECT_DIR/__pycache__"

echo "==> Preparing rpmbuild directories …"
RPM_TOPDIR="/tmp/rpmbuild"
rm -rf "$RPM_TOPDIR"
mkdir -p "$RPM_TOPDIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

echo "==> Copying source tree …"
shopt -s dotglob
for item in "$PROJECT_DIR"/*; do
    name="$(basename "$item")"
    case "$name" in
        .venv|.git|dist|build|__pycache__|*.egg-info) continue ;;
    esac
    cp -a "$item" "$RPM_TOPDIR/SOURCES/"
done
shopt -u dotglob

echo "==> Preparing spec file …"
sed "s/__VERSION__/$VERSION/g" "$SCRIPT_DIR/cutemd.spec" > "$RPM_TOPDIR/SPECS/cutemd.spec"

echo "==> Building RPM with rpmbuild …"
# rpmbuild will install uv, sync deps, and build PyInstaller inside %build
rpmbuild -bb \
    --define "_topdir $RPM_TOPDIR" \
    "$RPM_TOPDIR/SPECS/cutemd.spec"

echo "==> Collecting package …"
mkdir -p "$DIST_DIR"
cp "$RPM_TOPDIR"/RPMS/x86_64/*.rpm "$DIST_DIR/" 2>/dev/null || true

echo ""
echo "==> ✅  RPM built: dist/$APP-$VERSION-1.*.rpm"
echo "    Install with:  sudo dnf install dist/$APP-$VERSION-1.*.rpm"

rm -rf "$RPM_TOPDIR"
