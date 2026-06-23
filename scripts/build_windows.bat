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
    --onedir ^
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
    --hidden-import PySide6.QtSvg ^
    --hidden-import PySide6.QtPdf ^
    --exclude-module markdown ^
    main.py

echo ==> ✅  Executable built: dist\%APP%\%APP%.exe
echo     Distribute the entire dist\%APP%\ folder.
echo.
echo ==> Creating installer with Inno Setup ...
echo ==> DEBUG: searching iscc...
where iscc >nul 2>&1
echo ==> DEBUG: ERRORLEVEL=%ERRORLEVEL%
if %ERRORLEVEL% equ 0 (
    iscc scripts\cutemd_setup.iss
    echo ==> ✅  Installer built: dist\CuteMD_Setup.exe
) else (
    echo     Inno Setup not found on PATH -- skipping installer.
    echo     Install from https://jrsoftware.org/isinfo.php and run:
    echo       iscc scripts\cutemd_setup.iss
)
