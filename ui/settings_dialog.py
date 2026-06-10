"""Settings dialog — currently only theme selection."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from ui.themes import ALL_THEMES, get_theme


class SettingsDialog(QDialog):
    """A dialog for adjusting application settings.

    Currently only provides a theme picker with a live preview.
    """

    def __init__(self, current_theme_id: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # --- Theme section ---
        form = QFormLayout()

        self._theme_combo = QComboBox()
        for i, t in enumerate(ALL_THEMES):
            self._theme_combo.addItem(t.name, t.id)
            if t.id == current_theme_id:
                self._theme_combo.setCurrentIndex(i)

        form.addRow("Theme:", self._theme_combo)
        layout.addLayout(form)

        # Preview label
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(40)
        self._preview.setStyleSheet(
            "padding: 12px; border-radius: 6px; font-size: 13px;"
        )
        layout.addWidget(self._preview)

        self._theme_combo.currentIndexChanged.connect(self._update_preview)
        self._update_preview()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_theme_id(self) -> str:
        return self._theme_combo.currentData()

    def _update_preview(self) -> None:
        """Refresh the preview label with the currently selected theme colours."""
        theme = get_theme(self._theme_combo.currentData())
        self._preview.setText(f"This is a preview of {theme.name}")
        self._preview.setStyleSheet(
            f"background: {theme.base.name()};"
            f"color: {theme.text.name()};"
            "padding: 12px; border-radius: 6px; font-size: 13px;"
        )
