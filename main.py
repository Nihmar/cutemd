"""Entry point for CuteMD – a non-WYSIWYG Markdown editor."""

__version__ = "0.9.1"

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_modern_style


def _resolve_icon() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys._MEIPASS) / "resources" / "cutemd.svg")  # type: ignore[attr-defined]
    return str(Path(__file__).resolve().parent / "resources" / "cutemd.svg")


def main() -> None:
    app = QApplication(sys.argv)

    app.setApplicationName("CuteMD")
    app.setOrganizationName("cutemd")
    app.setWindowIcon(QIcon(_resolve_icon()))

    # Load translations (must be after org/app name so QSettings works)
    from ui.translations import setup_translation

    setup_translation(app)

    apply_modern_style(app)

    # Collect file paths passed as CLI arguments (e.g. "Open with CuteMD")
    files_to_open = [Path(a) for a in sys.argv[1:] if Path(a).is_file()]

    window = MainWindow(files_to_open=files_to_open if files_to_open else None)

    # Position on the screen where the cursor is located
    from PySide6.QtGui import QCursor, QGuiApplication

    screen = QGuiApplication.screenAt(QCursor.pos())
    if screen is not None:
        geo = screen.availableGeometry()
        frame = window.frameGeometry()
        frame.moveCenter(geo.center())
        window.move(frame.topLeft())

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
