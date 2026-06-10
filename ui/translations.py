"""Translation management for CuteMD.

Usage
-----
On startup, in ``main.py``::

    from ui.translations import setup_translation
    setup_translation(app)

.. codeauthor:: CuteMD Contributors
"""

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QTranslator
from PySide6.QtWidgets import QApplication

# (code, display_name) pairs for the language selector.
#   ""  →  no translation file (the built-in English fallback).
LANGUAGES: list[tuple[str, str]] = [
    ("", "System default"),
    ("it", "Italiano"),
]


def _translations_dir() -> Path:
    """Return the path to the ``resources/translations/`` directory."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources" / "translations"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / "resources" / "translations"


def load_translator(lang_code: str) -> QTranslator | None:
    """Load a ``.qm`` translation file for *lang_code*.

    Returns ``None`` when *lang_code* is empty or the file is missing.
    """
    if not lang_code:
        return None
    path = _translations_dir() / f"cutemd_{lang_code}.qm"
    translator = QTranslator()
    if translator.load(str(path)):
        return translator
    return None


def _current_translator(app: QApplication) -> QTranslator | None:
    """Return the currently installed translator for this app, if any."""
    return getattr(app, "_cutemd_translator", None)


def apply_language(app: QApplication, lang_code: str) -> None:
    """Install (or remove) a translator for *lang_code* **immediately**.

    Sends a ``LanguageChange`` event to every top-level widget so
    they can refresh their displayed strings.
    """
    old = _current_translator(app)
    if old is not None:
        app.removeTranslator(old)
        app._cutemd_translator = None  # type: ignore[attr-defined]

    translator = load_translator(lang_code)
    if translator is not None:
        app.installTranslator(translator)
        app._cutemd_translator = translator  # type: ignore[attr-defined]

    # Notify all open windows so they can retranslate
    from PySide6.QtCore import QEvent

    for widget in app.topLevelWidgets():
        app.sendEvent(widget, QEvent(QEvent.Type.LanguageChange))


def setup_translation(app: QApplication) -> None:
    """Read the saved language preference and install a translator.

    Must be called **after** ``QApplication`` has been created and
    ``setOrganizationName`` / ``setApplicationName`` have been set so
    that ``QSettings`` finds the correct storage.
    """
    settings = QSettings("cutemd", "cutemd")
    lang_code = str(settings.value("language", ""))
    apply_language(app, lang_code)
