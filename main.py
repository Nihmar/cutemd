"""Entry point for CuteMD – a non-WYSIWYG Markdown editor.

Startup sequence:
1. Create QApplication, set org/app name for QSettings
2. Set window icon (PyInstaller-aware path)
3. Load translations (must be after org/app name is set)
4. Apply modern style / theme
5. Collect CLI file arguments for "Open with" support
6. Create MainWindow (UI setup, geometry restore, last-folder restore)
7. Position window on the screen where the cursor is
8. Show window and enter event loop
"""

__version__ = "1.0.2"

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.logging import setup_logging
from ui.main_window import MainWindow
from ui.theme import apply_modern_style

_LOG = setup_logging("cutemd.main")


def _resolve_icon() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys._MEIPASS) / "resources" / "cutemd.svg")  # type: ignore[attr-defined]
    return str(Path(__file__).resolve().parent / "resources" / "cutemd.svg")


def main() -> None:
    _LOG.debug("CuteMD v%s starting (Python %s, %s)", __version__, sys.version.split()[0], sys.platform)

    app = QApplication(sys.argv)

    app.setApplicationName("CuteMD")
    app.setOrganizationName("cutemd")
    app.setWindowIcon(QIcon(_resolve_icon()))
    _LOG.debug("App name=%s org=%s", app.applicationName(), app.organizationName())

    from ui.translations import setup_translation

    lang = setup_translation(app)
    _LOG.debug("Translation loaded: %s", lang)

    apply_modern_style(app)
    _LOG.debug("Modern style applied")

    files_to_open = [Path(a) for a in sys.argv[1:] if Path(a).is_file()]
    if files_to_open:
        _LOG.debug("CLI files: %s", [f.name for f in files_to_open])

    window = MainWindow(files_to_open=files_to_open if files_to_open else None)
    _LOG.debug("MainWindow created")

    from PySide6.QtGui import QCursor, QGuiApplication

    screen = QGuiApplication.screenAt(QCursor.pos())
    if screen is not None:
        geo = screen.availableGeometry()
        frame = window.frameGeometry()
        frame.moveCenter(geo.center())
        window.move(frame.topLeft())
        _LOG.debug("Window positioned on screen: %s", screen.name())

    window.show()
    window.raise_()
    window.activateWindow()
    _LOG.debug("Window shown, entering event loop")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
