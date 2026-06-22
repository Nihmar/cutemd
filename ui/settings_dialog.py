"""Settings dialog — theme and font selection."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.markdown_completer import DEFAULT_SMART_EDITING
from ui.themes import ALL_THEMES, get_theme
from ui.translations import LANGUAGES


class _FontPicker(QWidget):
    """Search field + scrollable filtered list for font selection."""

    _LIST_HEIGHT = 150

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._edit = QLineEdit()
        self._edit.setClearButtonEnabled(True)
        lay.addWidget(self._edit)

        self._list = QListWidget()
        self._list.setFixedHeight(self._LIST_HEIGHT)
        lay.addWidget(self._list)

        self._edit.textChanged.connect(self._apply_filter)

    # --- populate / select ---

    def add_item(self, text: str, data: str) -> None:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, data)
        self._list.addItem(item)

    def select_by_data(self, data: str) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == data:
                self._list.setCurrentRow(i)
                self._list.scrollToItem(item)
                return
        if self._list.count():
            self._list.setCurrentRow(0)

    def select_first(self) -> None:
        self._edit.clear()
        if self._list.count():
            self._list.setCurrentRow(0)
            self._list.scrollToItem(self._list.item(0))

    # --- filter ---

    def _apply_filter(self, text: str) -> None:
        ft = text.lower()
        first_visible = None
        for i in range(self._list.count()):
            item = self._list.item(i)
            visible = (not ft) or (ft in item.text().lower())
            item.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = item
        # auto-select first visible when current selection is hidden
        cur = self._list.currentItem()
        if cur is None or cur.isHidden():
            if first_visible is not None:
                self._list.setCurrentItem(first_visible)
                self._list.scrollToItem(first_visible)

    # --- result ---

    def current_data(self) -> str:
        item = self._list.currentItem()
        if item is not None:
            return item.data(Qt.ItemDataRole.UserRole)
        return "System"


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
        current_smart_editing: dict[str, Any] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.setMinimumWidth(600)

        smart = dict(DEFAULT_SMART_EDITING)
        if current_smart_editing:
            smart.update(current_smart_editing)

        main_layout = QHBoxLayout(self)

        # --- Left panel: section list ---
        self._section_list = QListWidget()
        self._section_list.setFixedWidth(140)
        sections = [
            self.tr("Language"),
            self.tr("Theme"),
            self.tr("Editor"),
            self.tr("Preview Font"),
        ]
        for name in sections:
            self._section_list.addItem(name)
        main_layout.addWidget(self._section_list)

        # --- Right panel ---
        right = QVBoxLayout()

        self._stack = QStackedWidget()

        # Page 0: Language
        lang_page = self._build_page(self.tr("Language"))
        lang_page_layout = lang_page.layout()
        lang_form = QFormLayout()
        self._lang_combo = QComboBox()
        for i, (code, name) in enumerate(LANGUAGES):
            self._lang_combo.addItem(name, code)
            if code == current_language:
                self._lang_combo.setCurrentIndex(i)
        lang_form.addRow(self.tr("Language:"), self._lang_combo)
        lang_page_layout.addLayout(lang_form)
        lang_page_layout.addStretch()
        self._stack.addWidget(lang_page)

        # Page 1: Theme
        theme_page = self._build_page(self.tr("Theme"))
        theme_page_layout = theme_page.layout()
        theme_form = QFormLayout()
        self._theme_combo = QComboBox()
        for i, t in enumerate(ALL_THEMES):
            self._theme_combo.addItem(self.tr(t.name), t.id)
            if t.id == current_theme_id:
                self._theme_combo.setCurrentIndex(i)
        theme_form.addRow(self.tr("Theme:"), self._theme_combo)
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(40)
        self._preview.setStyleSheet(
            "padding: 12px; border-radius: 6px; font-size: 13px;"
        )
        theme_form.addRow(self._preview)
        self._theme_combo.currentIndexChanged.connect(self._update_preview)
        theme_page_layout.addLayout(theme_form)
        theme_page_layout.addStretch()
        self._stack.addWidget(theme_page)

        # Page 2: Editor
        editor_page = self._build_page(self.tr("Editor"))
        editor_page_layout = editor_page.layout()
        editor_form = QFormLayout()
        self._editor_font_combo = _FontPicker()
        self._populate_font_picker(self._editor_font_combo, current_editor_font)
        editor_form.addRow(self.tr("Font family:"), self._editor_font_combo)
        self._editor_font_size = QSpinBox()
        self._editor_font_size.setRange(8, 72)
        self._editor_font_size.setValue(current_editor_font_size)
        editor_form.addRow(self.tr("Font size:"), self._editor_font_size)
        self._line_number_combo = QComboBox()
        self._line_number_combo.addItem(self.tr("Off"), 0)
        self._line_number_combo.addItem(self.tr("All lines"), 1)
        self._line_number_combo.addItem(self.tr("Every 5th line"), 2)
        for i in range(self._line_number_combo.count()):
            if self._line_number_combo.itemData(i) == current_line_number_mode:
                self._line_number_combo.setCurrentIndex(i)
                break
        editor_form.addRow(self.tr("Line numbers:"), self._line_number_combo)
        editor_page_layout.addLayout(editor_form)

        # Smart editing checkboxes
        smart_group = QGroupBox(self.tr("Smart Editing"))
        smart_layout = QVBoxLayout(smart_group)

        self._smart_enabled = QCheckBox(self.tr("Enable smart editing"))
        self._smart_enabled.setChecked(smart["enabled"])

        self._auto_pair_cb = QCheckBox(
            self.tr("Auto-pair delimiters (*, _, ~, `)")
        )
        self._auto_pair_cb.setChecked(smart["auto_pair"])

        self._auto_brackets_cb = QCheckBox(
            self.tr("Auto-pair brackets ([], ())")
        )
        self._auto_brackets_cb.setChecked(smart["auto_pair_brackets"])

        self._continue_lists_cb = QCheckBox(
            self.tr("Continue lists on Enter")
        )
        self._continue_lists_cb.setChecked(smart["continue_lists"])

        self._backspace_pairs_cb = QCheckBox(
            self.tr("Remove empty pairs on Backspace")
        )
        self._backspace_pairs_cb.setChecked(smart["backspace_pairs"])

        smart_layout.addWidget(self._smart_enabled)
        smart_layout.addWidget(self._auto_pair_cb)
        smart_layout.addWidget(self._auto_brackets_cb)
        smart_layout.addWidget(self._continue_lists_cb)
        smart_layout.addWidget(self._backspace_pairs_cb)

        # Slave sub-checkboxes to master
        self._smart_enabled.toggled.connect(self._auto_pair_cb.setEnabled)
        self._smart_enabled.toggled.connect(self._auto_brackets_cb.setEnabled)
        self._smart_enabled.toggled.connect(self._continue_lists_cb.setEnabled)
        self._smart_enabled.toggled.connect(self._backspace_pairs_cb.setEnabled)
        # Initial enabled state
        enabled = smart["enabled"]
        self._auto_pair_cb.setEnabled(enabled)
        self._auto_brackets_cb.setEnabled(enabled)
        self._continue_lists_cb.setEnabled(enabled)
        self._backspace_pairs_cb.setEnabled(enabled)

        editor_page_layout.addWidget(smart_group)
        editor_page_layout.addStretch()
        self._stack.addWidget(editor_page)

        # Page 3: Preview Font
        preview_page = self._build_page(self.tr("Preview Font"))
        preview_page_layout = preview_page.layout()
        preview_form = QFormLayout()
        self._preview_font_combo = _FontPicker()
        self._populate_font_picker(self._preview_font_combo, current_preview_font)
        preview_form.addRow(self.tr("Family:"), self._preview_font_combo)
        self._preview_font_size = QSpinBox()
        self._preview_font_size.setRange(8, 72)
        self._preview_font_size.setValue(current_preview_font_size)
        preview_form.addRow(self.tr("Size:"), self._preview_font_size)
        preview_page_layout.addLayout(preview_form)
        preview_page_layout.addStretch()
        self._stack.addWidget(preview_page)

        right.addWidget(self._stack)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._defaults_btn = QPushButton(self.tr("Defaults"))
        buttons.addButton(self._defaults_btn, QDialogButtonBox.ButtonRole.ResetRole)
        self._defaults_btn.clicked.connect(self._reset_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)

        main_layout.addLayout(right)

        # Connect list to stack
        self._section_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._section_list.setCurrentRow(0)

        self._update_preview()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_page(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setLayout(QVBoxLayout())
        return group

    def _populate_font_picker(self, picker: _FontPicker, current: str) -> None:
        """Fill a font picker with 'System' + all available font families."""
        picker._edit.setPlaceholderText(self.tr("Type to filter\u2026"))
        picker.add_item(self.tr("System"), "System")
        db = QFontDatabase()
        for family in sorted(db.families()):
            picker.add_item(family, family)
        picker.select_by_data(current if current else "System")

    def _reset_defaults(self) -> None:
        """Reset all fields to their factory defaults."""
        self._lang_combo.setCurrentIndex(0)
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == "system":
                self._theme_combo.setCurrentIndex(i)
                break
        self._editor_font_combo.select_first()
        self._editor_font_size.setValue(11)
        self._line_number_combo.setCurrentIndex(1)  # all lines
        self._preview_font_combo.select_first()
        self._preview_font_size.setValue(16)
        # Smart editing defaults
        self._smart_enabled.setChecked(True)
        self._auto_pair_cb.setChecked(True)
        self._auto_brackets_cb.setChecked(True)
        self._continue_lists_cb.setChecked(True)
        self._backspace_pairs_cb.setChecked(True)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def selected_theme_id(self) -> str:
        return self._theme_combo.currentData()

    def selected_editor_font(self) -> str:
        return self._editor_font_combo.current_data()

    def selected_editor_font_size(self) -> int:
        return self._editor_font_size.value()

    def selected_preview_font(self) -> str:
        return self._preview_font_combo.current_data()

    def selected_preview_font_size(self) -> int:
        return self._preview_font_size.value()

    def selected_language(self) -> str:
        return self._lang_combo.currentData()

    def selected_line_number_mode(self) -> int:
        return self._line_number_combo.currentData()

    def selected_smart_editing(self) -> dict[str, Any]:
        return {
            "enabled": self._smart_enabled.isChecked(),
            "auto_pair": self._auto_pair_cb.isChecked(),
            "auto_pair_brackets": self._auto_brackets_cb.isChecked(),
            "continue_lists": self._continue_lists_cb.isChecked(),
            "backspace_pairs": self._backspace_pairs_cb.isChecked(),
        }

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
