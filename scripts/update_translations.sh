#!/usr/bin/env bash
# ------------------------------------------------------------------
#  update_translations.sh
#  Scan Python source files for translatable strings (tr() calls)
#  and update the .ts files, then compile them to .qm.
#
#  Prerequisites:
#    pip install pyside6
# ------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TRANSLATIONS_DIR="$PROJECT_DIR/resources/translations"

# Prefer the venv's own tools (avoids PATH issues)
VENV_PYSIDE6="$PROJECT_DIR/.venv/bin/pyside6"
LUPDATE="${VENV_PYSIDE6}-lupdate"
LRELEASE="${VENV_PYSIDE6}-lrelease"

# Fall back to PATH if not found in the venv
[ -x "$LUPDATE" ] || LUPDATE="pyside6-lupdate"
[ -x "$LRELEASE" ] || LRELEASE="pyside6-lrelease"

SOURCE_DIRS=("$PROJECT_DIR/ui" "$PROJECT_DIR/main.py")

LANGUAGES=("it")

# Default extensions exclude Python; we must opt in.
EXTENSIONS="py,ui"

echo "=== Updating .ts files ==="
for lang in "${LANGUAGES[@]}"; do
    ts_file="$TRANSLATIONS_DIR/cutemd_${lang}.ts"
    if [ -f "$ts_file" ]; then
        "$LUPDATE" -extensions "$EXTENSIONS" "${SOURCE_DIRS[@]}" -ts "$ts_file" -no-obsolete
    else
        "$LUPDATE" -extensions "$EXTENSIONS" "${SOURCE_DIRS[@]}" -ts "$ts_file"
    fi
    echo "  Updated: $ts_file"
done

echo ""
echo "=== Compiling .qm files ==="
for lang in "${LANGUAGES[@]}"; do
    ts_file="$TRANSLATIONS_DIR/cutemd_${lang}.ts"
    qm_file="$TRANSLATIONS_DIR/cutemd_${lang}.qm"
    "$LRELEASE" "$ts_file" -qm "$qm_file"
    echo "  Compiled: $qm_file"
done

echo ""
echo "Done."
