"""Entry point for CuteMD – a non-WYSIWYG Markdown editor."""

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_modern_style


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("CuteMD")
    app.setOrganizationName("cutemd")

    # Load translations (must be after org/app name so QSettings works)
    from ui.translations import setup_translation

    setup_translation(app)

    apply_modern_style(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
