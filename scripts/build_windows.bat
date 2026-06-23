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
    --add-data "resources/cutemd.ico;resources" ^
    --icon resources/cutemd.ico ^
    --version-file scripts/file_version_info.txt ^
    --collect-data latex2mathml ^
    --hidden-import PySide6.QtSvg ^
    --hidden-import PySide6.QtPdf ^
    --hidden-import PySide6.QtWebEngineWidgets ^
    --hidden-import PySide6.QtWebEngineCore ^
    --hidden-import requests ^
    main.py

echo ==> ✅  Executable built: dist\%APP%\%APP%.exe
echo     Distribute the entire dist\%APP%\ folder.
echo.
echo ==> Creating installer with Inno Setup ...
set ISCC=
for %%d in ("%ProgramFiles(x86)%\Inno Setup 6" "%ProgramFiles%\Inno Setup 6") do (
    if exist "%%~d\iscc.exe" set ISCC="%%~d\iscc.exe"
)
if not defined ISCC where iscc >nul 2>&1 && set ISCC=iscc
if defined ISCC (
    %ISCC% scripts\cutemd_setup.iss
    echo ==> ✅  Installer built: dist\CuteMD_Setup.exe
) else (
    echo     Inno Setup not found - install from https://jrsoftware.org/isinfo.php
    echo     Expected at: "%ProgramFiles(x86)%\Inno Setup 6\iscc.exe"
)
