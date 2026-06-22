"""Settings dialog — theme and font selection."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ui.themes import ALL_THEMES, get_theme
from ui.translations import LANGUAGES


class _ScrollingCombo(QComboBox):
    """QComboBox that limits its popup view to ~20 visible items."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMaxVisibleItems(20)


class SettingsDialog(QDialog):
    """A dialog for adjusting application settings.

    Provides a language selector, a theme picker with live preview,
    and font family/size selection for both the editor and preview pane.
    """

    def __init__(
        self,
        current_theme_id: str,
        current_editor_font: str,
        current_editor_font_size: int,
        current_preview_font: str,
        current_preview_font_size: int,
        current_language: str = "",
        current_line_number_mode: int = 1,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # --- Language section ---
        lang_group = QGroupBox(self.tr("Language"))
        lang_layout = QFormLayout(lang_group)

        self._lang_combo = QComboBox()
        for i, (code, name) in enumerate(LANGUAGES):
            self._lang_combo.addItem(name, code)
            if code == current_language:
                self._lang_combo.setCurrentIndex(i)

        lang_layout.addRow(self.tr("Language:"), self._lang_combo)
        layout.addWidget(lang_group)

        # --- Theme section ---
        theme_group = QGroupBox(self.tr("Theme"))
        theme_layout = QFormLayout(theme_group)

        self._theme_combo = QComboBox()
        for i, t in enumerate(ALL_THEMES):
            self._theme_combo.addItem(self.tr(t.name), t.id)
            if t.id == current_theme_id:
                self._theme_combo.setCurrentIndex(i)

        theme_layout.addRow(self.tr("Theme:"), self._theme_combo)

        # Preview label
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(40)
        self._preview.setStyleSheet(
            "padding: 12px; border-radius: 6px; font-size: 13px;"
        )
        theme_layout.addRow(self._preview)

        self._theme_combo.currentIndexChanged.connect(self._update_preview)
        layout.addWidget(theme_group)

        # --- Editor section ---
        editor_group = QGroupBox(self.tr("Editor"))
        editor_layout = QFormLayout(editor_group)

        self._editor_font_combo = _ScrollingCombo()
        self._populate_font_combo(self._editor_font_combo, current_editor_font)
        editor_layout.addRow(self.tr("Font family:"), self._editor_font_combo)

        self._editor_font_size = QSpinBox()
        self._editor_font_size.setRange(8, 72)
        self._editor_font_size.setValue(current_editor_font_size)
        editor_layout.addRow(self.tr("Font size:"), self._editor_font_size)

        self._line_number_combo = QComboBox()
        self._line_number_combo.addItem(self.tr("Off"), 0)
        self._line_number_combo.addItem(self.tr("All lines"), 1)
        self._line_number_combo.addItem(self.tr("Every 5th line"), 2)
        for i in range(self._line_number_combo.count()):
            if self._line_number_combo.itemData(i) == current_line_number_mode:
                self._line_number_combo.setCurrentIndex(i)
                break
        editor_layout.addRow(self.tr("Line numbers:"), self._line_number_combo)

        layout.addWidget(editor_group)

        # --- Preview Font section ---
        preview_group = QGroupBox(self.tr("Preview Font"))
        preview_layout = QFormLayout(preview_group)

        self._preview_font_combo = _ScrollingCombo()
        self._populate_font_combo(self._preview_font_combo, current_preview_font)
        preview_layout.addRow(self.tr("Family:"), self._preview_font_combo)

        self._preview_font_size = QSpinBox()
        self._preview_font_size.setRange(8, 72)
        self._preview_font_size.setValue(current_preview_font_size)
        preview_layout.addRow(self.tr("Size:"), self._preview_font_size)

        layout.addWidget(preview_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._defaults_btn = QPushButton(self.tr("Defaults"))
        buttons.addButton(self._defaults_btn, QDialogButtonBox.ButtonRole.ResetRole)
        self._defaults_btn.clicked.connect(self._reset_defaults)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_preview()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _populate_font_combo(self, combo: QComboBox, current: str) -> None:
        """Fill a combo box with 'System' + all available font families."""
        combo.addItem(self.tr("System"), "System")
        db = QFontDatabase()
        families = sorted(db.families())
        for i, family in enumerate(families, start=1):
            combo.addItem(family, family)
            if family == current:
                combo.setCurrentIndex(i)
        # If current is "System" (or not found), leave at index 0

    def _reset_defaults(self) -> None:
        """Reset all fields to their factory defaults."""
        self._lang_combo.setCurrentIndex(0)
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == "system":
                self._theme_combo.setCurrentIndex(i)
                break
        self._editor_font_combo.setCurrentIndex(0)
        self._editor_font_size.setValue(11)
        self._line_number_combo.setCurrentIndex(1)  # all lines
        self._preview_font_combo.setCurrentIndex(0)
        self._preview_font_size.setValue(16)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def selected_theme_id(self) -> str:
        return self._theme_combo.currentData()

    def selected_editor_font(self) -> str:
        return self._editor_font_combo.currentData()

    def selected_editor_font_size(self) -> int:
        return self._editor_font_size.value()

    def selected_preview_font(self) -> str:
        return self._preview_font_combo.currentData()

    def selected_preview_font_size(self) -> int:
        return self._preview_font_size.value()

    def selected_language(self) -> str:
        return self._lang_combo.currentData()

    def selected_line_number_mode(self) -> int:
        return self._line_number_combo.currentData()

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        """Refresh the preview label with the currently selected theme colours."""
        theme = get_theme(self._theme_combo.currentData())
        self._preview.setText(self.tr("This is a preview of {}").format(theme.name))
        self._preview.setStyleSheet(
            f"background: {theme.base.name()};"
            f"color: {theme.text.name()};"
            "padding: 12px; border-radius: 6px; font-size: 13px;"
        )
