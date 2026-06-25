%define _disable_source_fetch 1
%define _topdir /tmp/rpmbuild
%global debug_package %{nil}

Name: cutemd
Version: __VERSION__
Release: 1%{?dist}
Summary: A non-WYSIWYG Markdown editor with live preview
License: MIT
URL: https://github.com/Nihmar/cutemd
BuildArch: x86_64
BuildRequires: python3
Requires: desktop-file-utils
Requires: hicolor-icon-theme

%description
CuteMD is a Markdown editor featuring split editor/preview,
syntax highlighting, folder-based project navigation,
WebDAV cloud sync, and 9 built-in themes.
It supports both vault-style folder management and single-file edit mode.

%prep
%setup -q -c -T
cp -a %{_sourcedir}/* .

%build
curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --no-modify-path
export PATH="$HOME/.local/bin:$PATH"
uv sync
uv pip install pyinstaller
uv run pyinstaller \
    --name cutemd \
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

%install
install -d %{buildroot}/opt/cutemd
cp -r dist/cutemd/* %{buildroot}/opt/cutemd/
install -d %{buildroot}/usr/bin
ln -s /opt/cutemd/cutemd %{buildroot}/usr/bin/cutemd
install -d %{buildroot}/usr/share/applications
install -m 644 resources/cutemd.desktop %{buildroot}/usr/share/applications/
install -d %{buildroot}/usr/share/icons/hicolor/scalable/apps
install -m 644 resources/cutemd.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/

%post
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache /usr/share/icons/hicolor || true
fi

%postun
if [ "$1" = "0" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database /usr/share/applications || true
    fi
fi

%files
/opt/cutemd/
/usr/bin/cutemd
/usr/share/applications/cutemd.desktop
/usr/share/icons/hicolor/scalable/apps/cutemd.svg

%changelog
* __DATE__ - __VERSION__
- Initial RPM release
