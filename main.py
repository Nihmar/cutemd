"""Entry point for CuteMD – a non-WYSIWYG Markdown editor."""

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

    if "--install-desktop" in sys.argv:
        from ui.desktop_integration import install_desktop

        try:
            install_desktop()
            print("Desktop integration installed successfully.")
        except OSError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    app.setApplicationName("CuteMD")
    app.setOrganizationName("cutemd")
    app.setWindowIcon(QIcon(_resolve_icon()))

    # Load translations (must be after org/app name so QSettings works)
    from ui.translations import setup_translation

    setup_translation(app)

    apply_modern_style(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
