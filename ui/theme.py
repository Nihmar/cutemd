"""Theme support: colour palettes, Pygments style, and modern QSS."""

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Pygments style name — mutated by MainWindow._apply_theme()
PYGMENTS_STYLE: str = "monokai"

_STYLE_QSS: str | None = None  # cached stylesheet


def _load_qss() -> str:
    """Load the modern QSS stylesheet (cached after first read)."""
    global _STYLE_QSS
    if _STYLE_QSS is None:
        path = Path(__file__).resolve().parent / "style.qss"
        _STYLE_QSS = path.read_text() if path.exists() else ""
    return _STYLE_QSS


def dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.WindowText, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Text, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    p.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    return p


def light_palette() -> QPalette:
    """Return the default (light) system palette."""
    return QApplication.style().standardPalette()


def apply_modern_style(app: QApplication) -> None:
    """Apply the Fusion style and load the custom QSS stylesheet."""
    app.setStyle("Fusion")
    app.setStyleSheet(_load_qss())
