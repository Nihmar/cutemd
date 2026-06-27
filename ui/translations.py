"""Translation management for CuteMD.

Usage
-----
On startup, in ``main.py``::

    from ui.translations import setup_translation
    setup_translation(app)

.. codeauthor:: CuteMD Contributors
"""

from pathlib import Path

from core.paths import resolve_path
from PySide6.QtCore import QLocale, QSettings, QTranslator
from PySide6.QtWidgets import QApplication

# (code, display_name) pairs for the language selector.
LANGUAGES: list[tuple[str, str]] = [
    ("system", "System default"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fr", "Français"),
    ("it", "Italiano"),
    ("nl", "Nederlands"),
    ("pt", "Português"),
]


def _translations_dir() -> Path:
    """Return the path to the ``resources/translations/`` directory."""
    return resolve_path("resources", "translations")


def _resolve_lang_code(lang_code: str) -> str:
    """Resolve ``"system"`` (or empty string) to the OS locale code."""
    if not lang_code or lang_code == "system":
        return QLocale.system().name()[:2]
    return lang_code


def load_translator(lang_code: str) -> QTranslator | None:
    """Load a ``.qm`` translation file for *lang_code*.

    Returns ``None`` when the code is empty or the file is missing.
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

    ``"system"`` (or empty) is resolved to the OS locale.
    Sends a ``LanguageChange`` event to every top-level widget so
    they can refresh their displayed strings.
    """
    resolved = _resolve_lang_code(lang_code)

    old = _current_translator(app)
    if old is not None:
        app.removeTranslator(old)
        app._cutemd_translator = None  # type: ignore[attr-defined]

    translator = load_translator(resolved)
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
    lang_code = str(settings.value("language", "system"))
    apply_language(app, lang_code)
