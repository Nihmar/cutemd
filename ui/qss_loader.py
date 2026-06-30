"""Theme support: QSS generation from palette colours."""

from core.logging import setup_logging
from core.paths import resolve_path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

_LOG = setup_logging("cutemd.theme")
_STYLE_TEMPLATE: str | None = None
_QSS_CACHE: dict[int, str] = {}
_QSS_CACHE_MAX = 16  # one entry per theme palette, bounded


def _load_template() -> str:
    global _STYLE_TEMPLATE
    if _STYLE_TEMPLATE is None:
        path = resolve_path("ui", "style.qss")
        _STYLE_TEMPLATE = path.read_text() if path.exists() else ""
    return _STYLE_TEMPLATE


def load_qss(pal: QPalette | None = None) -> str:
    """Return the QSS with palette colours resolved (cached per palette)."""
    _LOG.debug("load_qss: %s", resolve_path("ui", "style.qss"))
    if pal is None:
        app = QCoreApplication.instance()
        if app is None:
            return _load_template()
        pal = app.palette()  # type: ignore[attr-defined]

    cache_key = (
        hash(tuple(pal.color(role).name() for role in [
            QPalette.ColorRole.Window, QPalette.ColorRole.WindowText,
            QPalette.ColorRole.Base, QPalette.ColorRole.AlternateBase,
            QPalette.ColorRole.Text, QPalette.ColorRole.Button,
            QPalette.ColorRole.ButtonText, QPalette.ColorRole.Highlight,
            QPalette.ColorRole.HighlightedText, QPalette.ColorRole.Mid,
            QPalette.ColorRole.Midlight, QPalette.ColorRole.Dark,
            QPalette.ColorRole.Link, QPalette.ColorRole.ToolTipBase,
            QPalette.ColorRole.ToolTipText,
        ]))
    )
    if cache_key in _QSS_CACHE:
        return _QSS_CACHE[cache_key]

    def c(role: QPalette.ColorRole) -> str:
        return pal.color(role).name()  # type: ignore[attr-defined]

    mapping = {
        "WINDOW": c(QPalette.ColorRole.Window),
        "WINDOW_TEXT": c(QPalette.ColorRole.WindowText),
        "BASE": c(QPalette.ColorRole.Base),
        "ALT_BASE": c(QPalette.ColorRole.AlternateBase),
        "TEXT": c(QPalette.ColorRole.Text),
        "BUTTON": c(QPalette.ColorRole.Button),
        "BUTTON_TEXT": c(QPalette.ColorRole.ButtonText),
        "HIGHLIGHT": c(QPalette.ColorRole.Highlight),
        "HIGHLIGHTED_TEXT": c(QPalette.ColorRole.HighlightedText),
        "MID": c(QPalette.ColorRole.Mid),
        "MIDLIGHT": c(QPalette.ColorRole.Midlight),
        "DARK": c(QPalette.ColorRole.Dark),
        "LINK": c(QPalette.ColorRole.Link),
        "TOOLTIP_BASE": c(QPalette.ColorRole.ToolTipBase),
        "TOOLTIP_TEXT": c(QPalette.ColorRole.ToolTipText),
    }

    qss = _load_template()
    for key, value in mapping.items():
        qss = qss.replace("${" + key + "}", value)
    _QSS_CACHE[cache_key] = qss
    if len(_QSS_CACHE) > _QSS_CACHE_MAX:
        _QSS_CACHE.pop(next(iter(_QSS_CACHE)))
    return qss


def apply_modern_style(app: QApplication) -> None:
    """Apply the Fusion style and load the custom QSS stylesheet."""
    _LOG.debug("apply_modern_style")
    app.setStyle("Fusion")
    app.setStyleSheet(load_qss(app.palette()))
