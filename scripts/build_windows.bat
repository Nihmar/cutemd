@echo off
SETLOCAL

set APP=cutemd
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%.."

echo ==> Cleaning previous builds ...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist __pycache__ rmdir /s /q __pycache__
if exist *.spec del /q *.spec

echo ==> Installing PyInstaller ...
uv pip install pyinstaller

echo ==> Building Windows executable (optimised for speed) ...
uv run pyinstaller ^
    --name %APP% ^
    --onefile ^
    --windowed ^
    --strip ^
    --optimize 2 ^
    --noupx ^
    --noconfirm ^
    --add-data "ui/icons;ui/icons" ^
    --add-data "ui/style.qss;ui" ^
    --add-data "ui/preview_styles.css;ui" ^
    --add-data "resources/translations;resources/translations" ^
    --add-data "resources/cutemd.svg;resources" ^
    --collect-data latex2mathml ^
    --collect-data pygments ^
    --hidden-import PySide6.QtSvg ^
    main.py

echo ==> ✅  Executable built: dist\%APP%.exe
echo     Self-contained -- distribute this single file.
