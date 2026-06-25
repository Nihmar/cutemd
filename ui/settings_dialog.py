"""Settings dialog — theme and font selection."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.markdown_completer import DEFAULT_SMART_EDITING
from ui.shortcut_manager import DEFAULT_SHORTCUTS
from ui.themes import ALL_THEMES, get_theme
from ui.translations import LANGUAGES
from ui.webdav_sync import WebDAVClient

_FONT_FAMILIES: list[str] | None = None


class _FontPicker(QWidget):
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
        self._list.setFrameShape(QListWidget.Shape.NoFrame)
        self._list.setFixedHeight(self._LIST_HEIGHT)
        lay.addWidget(self._list)

        # Fissa l'altezza del widget contenitore, non solo della lista
        edit_h = self._edit.sizeHint().height()
        total_h = edit_h + lay.spacing() + self._LIST_HEIGHT
        self.setMaximumHeight(total_h)

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
        current_cursor_width: int = 2,
        current_link_style: str = "md",
        current_smart_editing: dict[str, Any] | None = None,
        folder_settings: Any = None,
        parent=None,
        current_webdav_url: str = "",
        current_webdav_user: str = "",
        current_webdav_pass: str = "",
        current_autosave_interval: int = 5,
        current_auto_sync_enabled: bool = False,
        current_auto_sync_interval: int = 300,
        current_sync_on_save: bool = False,
        current_session_restore_enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.setMinimumWidth(600)
        self._folder_settings = folder_settings

        smart = dict(DEFAULT_SMART_EDITING)
        if current_smart_editing:
            smart.update(current_smart_editing)

        main_layout = QHBoxLayout(self)

        # --- Left panel: section list ---
        self._section_list = QListWidget()
        self._section_list.setObjectName("sectionList")
        self._section_list.setSpacing(6)
        self._section_list.setFixedWidth(140)
        sections = [
            self.tr("Language"),
            self.tr("Theme"),
            self.tr("Editor"),
            self.tr("Preview Font"),
            self.tr("Storage"),
        ]
        self._shortcuts_idx = -1
        self._sync_idx = -1
        if folder_settings is not None:
            sections.append(self.tr("Shortcuts"))
            self._shortcuts_idx = len(sections) - 1
            sections.append(self.tr("Sync"))
            self._sync_idx = len(sections) - 1
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
        self._preview.setMinimumHeight(70)
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
        editor_form.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        editor_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
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

        self._cursor_width = QSpinBox()
        self._cursor_width.setRange(1, 5)
        self._cursor_width.setValue(current_cursor_width)
        self._cursor_width.setToolTip(self.tr("Cursor thickness in pixels"))
        editor_form.addRow(self.tr("Cursor width:"), self._cursor_width)

        self._link_style_combo = QComboBox()
        self._link_style_combo.addItem(self.tr("Markdown [text](url)"), "md")
        self._link_style_combo.addItem(self.tr("Wikilink [[page]]"), "wiki")
        for i in range(self._link_style_combo.count()):
            if self._link_style_combo.itemData(i) == current_link_style:
                self._link_style_combo.setCurrentIndex(i)
                break
        editor_form.addRow(self.tr("Link style:"), self._link_style_combo)

        editor_page_layout.addLayout(editor_form)

        # Per-folder: images directory
        self._images_dir_edit: QLineEdit | None = None
        if folder_settings is not None:
            img_form = QFormLayout()
            self._images_dir_edit = QLineEdit()
            self._images_dir_edit.setText(
                folder_settings.load().get("images_dir", "images")
            )
            self._images_dir_edit.setPlaceholderText("images")
            img_form.addRow(self.tr("Images folder:"), self._images_dir_edit)
            editor_page_layout.addLayout(img_form)

        # Smart editing checkboxes
        smart_group = QGroupBox(self.tr("Smart Editing"))
        smart_layout = QVBoxLayout(smart_group)

        self._smart_enabled = QCheckBox(self.tr("Enable smart editing"))
        self._smart_enabled.setChecked(smart["enabled"])

        self._auto_pair_cb = QCheckBox(self.tr("Auto-pair delimiters (*, _, ~, `)"))
        self._auto_pair_cb.setChecked(smart["auto_pair"])

        self._auto_brackets_cb = QCheckBox(self.tr("Auto-pair brackets ([], ())"))
        self._auto_brackets_cb.setChecked(smart["auto_pair_brackets"])

        self._continue_lists_cb = QCheckBox(self.tr("Continue lists on Enter"))
        self._continue_lists_cb.setChecked(smart["continue_lists"])

        self._backspace_pairs_cb = QCheckBox(self.tr("Remove empty pairs on Backspace"))
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

        # Autosave
        autosave_form = QFormLayout()
        self._autosave_spin = QSpinBox()
        self._autosave_spin.setRange(1, 300)
        self._autosave_spin.setSuffix(self.tr(" s"))
        self._autosave_spin.setToolTip(
            self.tr("Automatically save open files every N seconds")
        )
        self._autosave_spin.setValue(current_autosave_interval)
        autosave_form.addRow(self.tr("Autosave interval:"), self._autosave_spin)
        editor_page_layout.addLayout(autosave_form)

        editor_page_layout.addStretch()
        self._stack.addWidget(editor_page)

        # Page 3: Preview Font
        preview_page = self._build_page(self.tr("Preview Font"))
        preview_page_layout = preview_page.layout()
        preview_form = QFormLayout()
        preview_form.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        preview_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self._preview_font_combo = _FontPicker()
        self._populate_font_picker(self._preview_font_combo, current_preview_font)
        preview_form.addRow(self.tr("Font family:"), self._preview_font_combo)
        self._preview_font_size = QSpinBox()
        self._preview_font_size.setRange(8, 72)
        self._preview_font_size.setValue(current_preview_font_size)
        preview_form.addRow(self.tr("Font size:"), self._preview_font_size)
        preview_page_layout.addLayout(preview_form)
        preview_page_layout.addStretch()
        self._stack.addWidget(preview_page)

        # Page 4: Storage
        storage_page = self._build_page(self.tr("Storage"))
        storage_page_layout = storage_page.layout()
        storage_form = QFormLayout()

        qs_path = QSettings("cutemd", "cutemd").fileName()
        qs_label = QLabel(qs_path)
        qs_label.setWordWrap(True)
        qs_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        storage_form.addRow(self.tr("Config file:"), qs_label)

        self._dotdir_info = QLabel()
        storage_form.addRow(self.tr("Folder data (.cutemd):"), self._dotdir_info)

        storage_page_layout.addLayout(storage_form)

        clear_btn = QPushButton(self.tr("Clear last folder"))
        clear_btn.clicked.connect(self._clear_last_folder)
        storage_page_layout.addWidget(clear_btn)

        self._session_restore_cb = QCheckBox(self.tr("Restore open tabs on startup"))
        self._session_restore_cb.setChecked(current_session_restore_enabled)
        storage_page_layout.addWidget(self._session_restore_cb)

        storage_page_layout.addStretch()
        self._stack.addWidget(storage_page)

        # Page 5: Shortcuts (only when folder is open)
        if folder_settings is not None:
            current_shortcuts = folder_settings.load_shortcuts()
            shortcuts_page = self._build_page(self.tr("Shortcuts"))
            shortcuts_page_layout = shortcuts_page.layout()

            self._shortcuts_table = QTableWidget()
            self._shortcuts_table.setColumnCount(3)
            self._shortcuts_table.setHorizontalHeaderLabels(
                [
                    self.tr("Action"),
                    self.tr("Default"),
                    self.tr("Custom"),
                ]
            )
            self._shortcuts_table.horizontalHeader().setStretchLastSection(True)
            self._shortcuts_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
            self._shortcuts_table.verticalHeader().setVisible(False)
            self._shortcuts_table.setAlternatingRowColors(True)
            self._shortcuts_table.setSelectionMode(
                QTableWidget.SelectionMode.NoSelection
            )

            shortcut_rows = []
            for name, default_seq in DEFAULT_SHORTCUTS.items():
                custom = current_shortcuts.get(name, "")
                shortcut_rows.append((name, default_seq, custom))

            shortcut_rows.sort(key=lambda r: r[0])
            self._shortcuts_table.setRowCount(len(shortcut_rows))
            self._shortcut_keys: list[str] = []
            for i, (name, default_seq, custom) in enumerate(shortcut_rows):
                self._shortcuts_table.setItem(
                    i, 0, QTableWidgetItem(name.replace("act_", ""))
                )
                self._shortcuts_table.setItem(i, 1, QTableWidgetItem(default_seq))
                editor = QKeySequenceEdit()
                if custom:
                    editor.setKeySequence(QKeySequence(custom))
                editor.setMaximumWidth(160)
                self._shortcuts_table.setCellWidget(i, 2, editor)
                self._shortcut_keys.append(name)

            shortcuts_page_layout.addWidget(self._shortcuts_table)
            shortcuts_page_layout.addStretch()
            self._stack.addWidget(shortcuts_page)

        # Page N: Sync (only when folder is open)
        self._webdav_url_edit: QLineEdit | None = None
        self._webdav_user_edit: QLineEdit | None = None
        self._webdav_pass_edit: QLineEdit | None = None
        if folder_settings is not None:
            sync_page = self._build_page(self.tr("Sync"))
            sync_page_layout = sync_page.layout()
            sync_form = QFormLayout()

            self._webdav_url_edit = QLineEdit()
            self._webdav_url_edit.setPlaceholderText("https://dav.example.com/notes")
            self._webdav_url_edit.setText(current_webdav_url)
            sync_form.addRow(self.tr("URL:"), self._webdav_url_edit)

            self._webdav_user_edit = QLineEdit()
            self._webdav_user_edit.setPlaceholderText(self.tr("Username"))
            self._webdav_user_edit.setText(current_webdav_user)
            sync_form.addRow(self.tr("Username:"), self._webdav_user_edit)

            self._webdav_pass_edit = QLineEdit()
            self._webdav_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._webdav_pass_edit.setPlaceholderText(self.tr("Password"))
            self._webdav_pass_edit.setText(current_webdav_pass)
            sync_form.addRow(self.tr("Password:"), self._webdav_pass_edit)

            test_btn = QPushButton(self.tr("Test Connection"))
            test_btn.clicked.connect(self._on_test_webdav)
            sync_form.addRow("", test_btn)

            sync_page_layout.addLayout(sync_form)

            auto_group = QGroupBox(self.tr("Auto Sync"))
            auto_layout = QVBoxLayout(auto_group)

            self._auto_sync_cb = QCheckBox(self.tr("Auto-sync periodically"))
            self._auto_sync_cb.setChecked(current_auto_sync_enabled)
            auto_layout.addWidget(self._auto_sync_cb)

            interval_row = QHBoxLayout()
            interval_row.addWidget(QLabel(self.tr("Interval:")))
            self._auto_sync_interval = QSpinBox()
            self._auto_sync_interval.setRange(1, 3600)
            self._auto_sync_interval.setValue(current_auto_sync_interval)
            self._auto_sync_interval.setSuffix(self.tr(" s"))
            self._auto_sync_interval.setToolTip(self.tr("Sync every N seconds"))
            interval_row.addWidget(self._auto_sync_interval)
            interval_row.addStretch()
            auto_layout.addLayout(interval_row)

            self._sync_on_save_cb = QCheckBox(self.tr("Sync file immediately on save"))
            self._sync_on_save_cb.setChecked(current_sync_on_save)
            auto_layout.addWidget(self._sync_on_save_cb)

            self._auto_sync_cb.toggled.connect(self._auto_sync_interval.setEnabled)
            self._auto_sync_interval.setEnabled(current_auto_sync_enabled)

            sync_page_layout.addWidget(auto_group)
            sync_page_layout.addStretch()
            self._stack.addWidget(sync_page)

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
        self._refresh_storage_info()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_page(self, title: str = "") -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(8, 8, 8, 8)
        if title:
            header = QLabel(title)
            header.setStyleSheet(
                "font-weight: bold; font-size: 13px; padding: 0 0 8px 0;"
            )
            lay.addWidget(header)
        return widget

    def _populate_font_picker(self, picker: _FontPicker, current: str) -> None:
        """Fill a font picker with 'System' + all available font families."""
        global _FONT_FAMILIES
        picker._edit.setPlaceholderText(self.tr("Type to filter\u2026"))
        picker.add_item(self.tr("System"), "System")
        if _FONT_FAMILIES is None:
            _FONT_FAMILIES = sorted(QFontDatabase().families())
        for family in _FONT_FAMILIES:
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
        self._cursor_width.setValue(2)
        self._link_style_combo.setCurrentIndex(0)  # markdown links
        self._preview_font_combo.select_first()
        self._preview_font_size.setValue(16)
        # Smart editing defaults
        self._smart_enabled.setChecked(True)
        self._auto_pair_cb.setChecked(True)
        self._auto_brackets_cb.setChecked(True)
        self._continue_lists_cb.setChecked(True)
        self._backspace_pairs_cb.setChecked(True)
        # Autosave
        self._autosave_spin.setValue(5)
        # Session restore
        self._session_restore_cb.setChecked(False)
        # Images dir
        if self._images_dir_edit is not None:
            self._images_dir_edit.clear()
        # WebDAV
        if self._webdav_url_edit is not None:
            self._webdav_url_edit.clear()
        if self._webdav_user_edit is not None:
            self._webdav_user_edit.clear()
        if self._webdav_pass_edit is not None:
            self._webdav_pass_edit.clear()
        # Auto-sync
        if hasattr(self, "_auto_sync_cb"):
            self._auto_sync_cb.setChecked(False)
        if hasattr(self, "_auto_sync_interval"):
            self._auto_sync_interval.setValue(300)
        if hasattr(self, "_sync_on_save_cb"):
            self._sync_on_save_cb.setChecked(False)
        # Shortcuts
        if hasattr(self, "_shortcuts_table"):
            for i in range(self._shortcuts_table.rowCount()):
                editor = self._shortcuts_table.cellWidget(i, 2)
                if isinstance(editor, QKeySequenceEdit):
                    editor.clear()

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

    def selected_cursor_width(self) -> int:
        return self._cursor_width.value()

    def selected_link_style(self) -> str:
        return self._link_style_combo.currentData()

    def selected_smart_editing(self) -> dict[str, Any]:
        return {
            "enabled": self._smart_enabled.isChecked(),
            "auto_pair": self._auto_pair_cb.isChecked(),
            "auto_pair_brackets": self._auto_brackets_cb.isChecked(),
            "continue_lists": self._continue_lists_cb.isChecked(),
            "backspace_pairs": self._backspace_pairs_cb.isChecked(),
        }

    def selected_shortcuts(self) -> dict[str, str]:
        shortcuts: dict[str, str] = {}
        if hasattr(self, "_shortcuts_table"):
            for i in range(self._shortcuts_table.rowCount()):
                name = self._shortcut_keys[i]
                editor = self._shortcuts_table.cellWidget(i, 2)
                if isinstance(editor, QKeySequenceEdit):
                    seq = editor.keySequence()
                    if not seq.isEmpty():
                        shortcuts[name] = seq.toString(
                            QKeySequence.SequenceFormat.PortableText
                        )
        return shortcuts

    def selected_images_dir(self) -> str | None:
        if self._images_dir_edit is not None:
            return self._images_dir_edit.text().strip() or None
        return None

    def selected_autosave_interval(self) -> int:
        return self._autosave_spin.value()

    def selected_auto_sync_enabled(self) -> bool:
        if hasattr(self, "_auto_sync_cb"):
            return self._auto_sync_cb.isChecked()
        return False

    def selected_auto_sync_interval(self) -> int:
        if hasattr(self, "_auto_sync_interval"):
            return self._auto_sync_interval.value()
        return 300

    def selected_sync_on_save(self) -> bool:
        if hasattr(self, "_sync_on_save_cb"):
            return self._sync_on_save_cb.isChecked()
        return False

    def selected_session_restore_enabled(self) -> bool:
        return self._session_restore_cb.isChecked()

    def selected_webdav_url(self) -> str:
        if self._webdav_url_edit is not None:
            return self._webdav_url_edit.text().strip()
        return ""

    def selected_webdav_username(self) -> str:
        if self._webdav_user_edit is not None:
            return self._webdav_user_edit.text().strip()
        return ""

    def selected_webdav_password(self) -> str:
        if self._webdav_pass_edit is not None:
            return self._webdav_pass_edit.text()
        return ""

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _refresh_storage_info(self) -> None:
        if self._folder_settings is not None:
            size = self._folder_settings.dotdir_size()
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            path_str = str(self._folder_settings.dotdir_path)
            self._dotdir_info.setText(
                self.tr("{} \u2014 {}").format(path_str, size_str)
            )
        else:
            self._dotdir_info.setText(self.tr("No folder open"))

    def _clear_last_folder(self) -> None:
        QSettings("cutemd", "cutemd").remove("last_folder")
        QSettings("cutemd", "cutemd").remove("recent_folders")
        QMessageBox.information(
            self,
            self.tr("Storage"),
            self.tr(
                "Last folder and recent folders list cleared.\n"
                "You will be prompted to choose a folder on next launch."
            ),
        )

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

    # ------------------------------------------------------------------
    # Sync helpers
    # ------------------------------------------------------------------

    def _on_test_webdav(self) -> None:
        url = self._webdav_url_edit.text().strip() if self._webdav_url_edit else ""
        user = self._webdav_user_edit.text().strip() if self._webdav_user_edit else ""
        pw = self._webdav_pass_edit.text() if self._webdav_pass_edit else ""

        if not url:
            QMessageBox.warning(
                self, self.tr("Test Connection"), self.tr("Please enter a URL.")
            )
            return

        client = WebDAVClient(url, user, pw)
        ok, err = client.test_connection()
        if ok:
            QMessageBox.information(
                self,
                self.tr("Test Connection"),
                self.tr("Connection successful!"),
            )
        else:
            QMessageBox.warning(
                self,
                self.tr("Test Connection"),
                self.tr("Connection failed:\n{}").format(err),
            )
