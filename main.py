"""Entry point for CuteMD – a non-WYSIWYG Markdown editor."""

import sys

from main_window import MainWindow
from PySide6.QtWidgets import QApplication


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("CuteMD")
    app.setOrganizationName("cutemd")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
