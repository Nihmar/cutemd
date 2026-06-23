"""Generate resources/cutemd.ico from resources/cutemd.svg."""
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "resources" / "cutemd.svg"
ICO = ROOT / "resources" / "cutemd.ico"

SIZES = [16, 24, 32, 48, 64, 96, 128, 256]


def main() -> None:
    if not SVG.exists():
        print(f"Error: {SVG} not found", file=sys.stderr)
        sys.exit(1)

    renderer = QSvgRenderer(str(SVG))

    pixmaps: list[QPixmap] = []
    for size in SIZES:
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmaps.append(pixmap)

    # Combine into ICO: pick the largest pixmap and save with sizes
    main_pix = pixmaps[-1]
    main_img = main_pix.toImage()
    main_img.save(str(ICO), format="ICO")
    print(f"Created {ICO}")


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    main()
    app.quit()
