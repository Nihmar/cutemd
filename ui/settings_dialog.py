"""Settings dialog — theme and font selection (redesigned UI)."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.markdown_completer import DEFAULT_SMART_EDITING
from ui.shortcut_manager import DEFAULT_SHORTCUTS
from ui.themes import ALL_THEMES, get_theme
from ui.translations import LANGUAGES
from ui.widgets import CuteListWidget
from ui.widgets.font_picker import FontPicker, FontPreviewDelegate
from ui.widgets.toggle_switch import ToggleSwitch
from core.webdav.sync import WebDAVClient

_FONT_FAMILIES: list[str] | None = None


def _spell_available() -> bool:
    try:
        import enchant  # noqa: F401
        return True
    except ImportError:
        return False


# ======================================================================
# Font preview delegate — creates QFont lazily for visible items only
# ======================================================================



# ======================================================================
# Font loader thread — loads system fonts without blocking the UI
# ======================================================================


class _FontLoaderThread(QThread):
    result = Signal(list)

    def run(self) -> None:
        from PySide6.QtGui import QFontDatabase
        families = sorted(QFontDatabase().families())
        self.result.emit(families)

class _WebDAVTestWorker(QThread):
    result = Signal(bool, str)

    def __init__(self, url: str, user: str, pw: str):
        super().__init__()
        self._url = url
        self._user = user
        self._pw = pw

    def run(self) -> None:
        try:
            client = WebDAVClient(self._url, self._user, self._pw)
            ok, err = client.test_connection()
        except Exception as e:
            ok, err = False, str(e)
        self.result.emit(ok, err)


# ======================================================================
# Settings dialog
# ======================================================================


class SettingsDialog(QDialog):
    """A dialog for adjusting application settings.

    Redesigned with fixed dimensions, scrollable content areas,
    card-grouped sections, and toggle switches.
    """

    _DIALOG_W = 700
    _DIALOG_H = 560

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
        app_settings: Any = None,
        parent=None,
        current_webdav_url: str = "",
        current_webdav_user: str = "",
        current_webdav_pass: str = "",
        current_autosave_interval: int = 5,
        current_auto_sync_enabled: bool = False,
        current_auto_sync_interval: int = 300,
        current_sync_on_save: bool = False,
        current_session_restore_enabled: bool = False,
        current_show_hidden_files: bool = False,
        current_webdav_backup_dir: str = "",
        current_templates_dir: str = "",
        current_folder: str = "",
        current_daily_folder: str = "daily",
        current_daily_template: str = "",
        current_daily_date_format: str = "%Y-%m-%d",
        current_zen_mode_max_width: int = 800,
        current_toc_in_preview: bool = False,
        current_spell_check_lang: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.setFixedSize(self._DIALOG_W, self._DIALOG_H)
        self._folder_settings = folder_settings
        self._app_settings = app_settings
        self._current_folder = current_folder

        smart = dict(DEFAULT_SMART_EDITING)
        if current_smart_editing:
            smart.update(current_smart_editing)

        # Theme selection state
        self._selected_theme_id = current_theme_id

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left panel: sidebar ---
        self._section_list = CuteListWidget()
        self._section_list.setObjectName("sectionList")
        self._section_list.setFixedWidth(160)

        _icons = ["🌐", "🎨", "✏️", "👁️", "💾", "⌨️", "🔄"]
        _names = [
            self.tr("General"),
            self.tr("Theme"),
            self.tr("Editor"),
            self.tr("Preview Font"),
            self.tr("Storage"),
            self.tr("Shortcuts"),
            self.tr("Sync"),
        ]
        self._shortcuts_idx = 5
        self._sync_idx = 6
        for i, (icon, name) in enumerate(zip(_icons, _names)):
            item = QListWidgetItem(f"{icon}   {name}")
            if folder_settings is None and i in (self._shortcuts_idx, self._sync_idx):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._section_list.addItem(item)
        main_layout.addWidget(self._section_list)

        # --- Right panel ---
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self._stack = QStackedWidget()

        # ---- Page 0: General ----
        gen_scroll, gen_lay = self._build_page(
            self.tr("General"),
            self.tr("Interface language, update preferences, and other general settings"),
        )
        card, card_lay = self._make_card()

        # Language section
        card_lay.addWidget(self._section_label(self.tr("LANGUAGE")))
        self._lang_combo = QComboBox()
        match_lang = "system" if not current_language else current_language
        for i, (code, name) in enumerate(LANGUAGES):
            self._lang_combo.addItem(self.tr(name), code)
            if code == match_lang:
                self._lang_combo.setCurrentIndex(i)
        card_lay.addLayout(
            self._field_row(
                self.tr("Display language"),
                self._lang_combo,
                self.tr("Requires restart to apply"),
            )
        )

        # Auto-update section
        card_lay.addWidget(self._separator())
        card_lay.addWidget(self._section_label(self.tr("UPDATES")))
        self._auto_update_toggle = ToggleSwitch(
            self._app_settings.auto_update_check() if self._app_settings else True
        )
        card_lay.addLayout(
            self._field_row(
                self.tr("Check for updates automatically on startup"),
                self._auto_update_toggle,
            )
        )

        # Interface section
        card_lay.addWidget(self._separator())
        card_lay.addWidget(self._section_label(self.tr("INTERFACE")))
        self._menu_bar_toggle = ToggleSwitch(
            self._app_settings.menu_bar_visible() if self._app_settings else True
        )
        card_lay.addLayout(
            self._field_row(
                self.tr("Show menu bar"),
                self._menu_bar_toggle,
            )
        )
        gen_lay.addWidget(card)

        gen_lay.addSpacing(12)

        # Spell check
        if _spell_available():
            current_langs = set(
                x.strip() for x in current_spell_check_lang.split(",") if x.strip()
            )
            card, card_lay = self._make_card()
            lbl = QLabel(self.tr("Spell check languages"))
            lbl.setStyleSheet("font-size: 12px; font-weight: bold;")
            card_lay.addWidget(lbl)

            self._spell_check_lang_cbs: dict[str, QCheckBox] = {}
            try:
                import enchant
                all_langs = set(enchant.list_languages())
            except Exception:
                all_langs = set()
            from core.dict_manager import AVAILABLE_DICTS, is_dict_installed

            # Show UI languages first
            for ui_code, hunspell_code in AVAILABLE_DICTS.items():
                if hunspell_code in all_langs or is_dict_installed(hunspell_code):
                    cb = QCheckBox(f"{ui_code} ({hunspell_code})")
                    cb.setChecked(hunspell_code in current_langs)
                    card_lay.addWidget(cb)
                    self._spell_check_lang_cbs[hunspell_code] = cb

            # Show other installed dicts
            for lang in sorted(all_langs):
                if lang in self._spell_check_lang_cbs:
                    continue
                if lang.startswith("en_"):
                    continue
                cb = QCheckBox(lang)
                cb.setChecked(lang in current_langs)
                card_lay.addWidget(cb)
                self._spell_check_lang_cbs[lang] = cb

            gen_lay.addWidget(card)
        else:
            card, card_lay = self._make_card()
            lbl = QLabel(
                self.tr("Spell check requires pyenchant.\nInstall it with: pip install pyenchant")
            )
            lbl.setStyleSheet("font-size: 11px;")
            card_lay.addWidget(lbl)
            gen_lay.addWidget(card)
            self._spell_check_lang_cbs = {}

        gen_lay.addSpacing(12)

        # Dictionaries download
        if _spell_available():
            card, card_lay = self._make_card()
            lbl = QLabel(self.tr("Dictionaries"))
            lbl.setStyleSheet("font-size: 12px; font-weight: bold;")
            card_lay.addWidget(lbl)

            self._dict_status_labels: dict[str, QLabel] = {}
            self._dict_buttons: dict[str, QPushButton] = {}
            from core.dict_manager import AVAILABLE_DICTS, is_dict_installed

            for ui_code, hunspell_code in AVAILABLE_DICTS.items():
                row = QHBoxLayout()
                name = ui_code.upper() + " (" + hunspell_code + ")"
                status_lbl = QLabel(
                    "\u2705 " + name if is_dict_installed(hunspell_code)
                    else "\u2b1c " + name
                )
                row.addWidget(status_lbl)
                row.addStretch()

                if is_dict_installed(hunspell_code):
                    btn = QPushButton(self.tr("Uninstall"))
                    btn.setFixedWidth(90)
                    btn.clicked.connect(
                        lambda checked, c=hunspell_code: self._on_uninstall_dict(c)
                    )
                else:
                    btn = QPushButton(self.tr("Install"))
                    btn.setFixedWidth(90)
                    btn.clicked.connect(
                        lambda checked, c=hunspell_code: self._on_install_dict(c)
                    )
                row.addWidget(btn)
                card_lay.addLayout(row)
                self._dict_status_labels[hunspell_code] = status_lbl
                self._dict_buttons[hunspell_code] = btn

            gen_lay.addWidget(card)

        gen_lay.addStretch()
        self._stack.addWidget(gen_scroll)

        # ---- Page 1: Theme ----
        theme_scroll, theme_lay = self._build_page(
            self.tr("Theme"),
            self.tr("Pick a color scheme for the interface"),
        )
        theme_grid = QGridLayout()
        theme_grid.setSpacing(8)
        self._theme_swatch_btns: list[tuple[str, QPushButton]] = []
        for i, t in enumerate(ALL_THEMES):
            theme = get_theme(t.id)
            btn = QPushButton("Aa")
            btn.setFixedHeight(52)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(self.tr(t.name))
            btn.clicked.connect(lambda _, tid=t.id: self._select_theme(tid))
            self._theme_swatch_btns.append((t.id, btn))
            row, col = divmod(i, 3)
            # Container with swatch + label
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(btn)
            lbl = QLabel(self.tr(t.name))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 11px;")
            box.addWidget(lbl)
            theme_grid.addLayout(box, row, col)
        theme_lay.addLayout(theme_grid)
        theme_lay.addStretch()
        self._stack.addWidget(theme_scroll)
        self._update_theme_swatches()

        # ---- Page 2: Editor ----
        editor_scroll, editor_lay = self._build_page(
            self.tr("Editor"),
            self.tr("Font, display and editing behavior"),
        )

        # Section: Font
        editor_lay.addWidget(self._section_label(self.tr("FONT")))
        card, card_lay = self._make_card()
        self._editor_font_combo = FontPicker()
        self._editor_font_current = current_editor_font
        self._editor_font_populated = False
        f_row = QFormLayout()
        f_row.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        f_row.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        f_row.addRow(self.tr("Font family:"), self._editor_font_combo)
        card_lay.addLayout(f_row)
        card_lay.addWidget(self._separator())
        self._editor_font_size = QSpinBox()
        self._editor_font_size.setRange(8, 72)
        self._editor_font_size.setValue(current_editor_font_size)
        card_lay.addLayout(
            self._field_row(self.tr("Font size"), self._editor_font_size)
        )
        editor_lay.addWidget(card)

        # Section: Display
        editor_lay.addWidget(self._section_label(self.tr("DISPLAY")))
        card, card_lay = self._make_card()

        self._line_number_combo = QComboBox()
        self._line_number_combo.addItem(self.tr("Off"), 0)
        self._line_number_combo.addItem(self.tr("All lines"), 1)
        self._line_number_combo.addItem(self.tr("Every 5th line"), 2)
        for i in range(self._line_number_combo.count()):
            if self._line_number_combo.itemData(i) == current_line_number_mode:
                self._line_number_combo.setCurrentIndex(i)
                break
        card_lay.addLayout(
            self._field_row(self.tr("Line numbers"), self._line_number_combo)
        )
        card_lay.addWidget(self._separator())

        self._cursor_width = QSpinBox()
        self._cursor_width.setRange(1, 5)
        self._cursor_width.setValue(current_cursor_width)
        card_lay.addLayout(self._field_row(self.tr("Cursor width"), self._cursor_width))
        card_lay.addWidget(self._separator())

        self._link_style_combo = QComboBox()
        self._link_style_combo.addItem(self.tr("Markdown [text](url)"), "md")
        self._link_style_combo.addItem(self.tr("Wikilink [[page]]"), "wiki")
        for i in range(self._link_style_combo.count()):
            if self._link_style_combo.itemData(i) == current_link_style:
                self._link_style_combo.setCurrentIndex(i)
                break
        card_lay.addLayout(
            self._field_row(self.tr("Link style"), self._link_style_combo)
        )
        card_lay.addWidget(self._separator())

        self._show_hidden_toggle = ToggleSwitch(current_show_hidden_files)
        card_lay.addLayout(
            self._field_row(
                self.tr("Show hidden files"),
                self._show_hidden_toggle,
                self.tr("Display dotfiles in the sidebar"),
            )
        )
        editor_lay.addWidget(card)

        # Section: Smart editing
        editor_lay.addWidget(self._section_label(self.tr("SMART EDITING")))
        card, card_lay = self._make_card()

        self._smart_enabled = ToggleSwitch(smart["enabled"])
        card_lay.addLayout(
            self._field_row(self.tr("Enable smart editing"), self._smart_enabled)
        )
        card_lay.addWidget(self._separator())

        self._auto_pair_toggle = ToggleSwitch(smart["auto_pair"])
        card_lay.addLayout(
            self._field_row(
                self.tr("Auto-pair delimiters"),
                self._auto_pair_toggle,
                "*, _, ~, `",
            )
        )
        card_lay.addWidget(self._separator())

        self._auto_brackets_toggle = ToggleSwitch(smart["auto_pair_brackets"])
        card_lay.addLayout(
            self._field_row(
                self.tr("Auto-pair brackets"),
                self._auto_brackets_toggle,
                "[], ()",
            )
        )
        card_lay.addWidget(self._separator())

        self._continue_lists_toggle = ToggleSwitch(smart["continue_lists"])
        card_lay.addLayout(
            self._field_row(
                self.tr("Continue lists on enter"), self._continue_lists_toggle
            )
        )
        card_lay.addWidget(self._separator())

        self._backspace_pairs_toggle = ToggleSwitch(smart["backspace_pairs"])
        card_lay.addLayout(
            self._field_row(
                self.tr("Remove empty pairs on backspace"),
                self._backspace_pairs_toggle,
            )
        )

        # Master → slave
        self._smart_enabled.toggled.connect(self._auto_pair_toggle.setEnabled)
        self._smart_enabled.toggled.connect(self._auto_brackets_toggle.setEnabled)
        self._smart_enabled.toggled.connect(self._continue_lists_toggle.setEnabled)
        self._smart_enabled.toggled.connect(self._backspace_pairs_toggle.setEnabled)
        enabled = smart["enabled"]
        self._auto_pair_toggle.setEnabled(enabled)
        self._auto_brackets_toggle.setEnabled(enabled)
        self._continue_lists_toggle.setEnabled(enabled)
        self._backspace_pairs_toggle.setEnabled(enabled)

        editor_lay.addWidget(card)

        # Section: Autosave
        editor_lay.addWidget(self._section_label(self.tr("AUTO-SAVE")))
        card, card_lay = self._make_card()
        self._autosave_spin = QSpinBox()
        self._autosave_spin.setRange(1, 300)
        self._autosave_spin.setSuffix(self.tr(" s"))
        self._autosave_spin.setToolTip(
            self.tr("Automatically save open files every N seconds")
        )
        self._autosave_spin.setValue(current_autosave_interval)
        card_lay.addLayout(
            self._field_row(
                self.tr("Save interval"),
                self._autosave_spin,
                self.tr("Automatically save open files"),
            )
        )
        editor_lay.addWidget(card)
        editor_lay.addStretch()
        self._stack.addWidget(editor_scroll)

        # ---- Page 3: Preview Font ----
        prev_scroll, prev_lay = self._build_page(
            self.tr("Preview Font"),
            self.tr("Typography for the markdown preview pane"),
        )
        card, card_lay = self._make_card()
        self._preview_font_combo = FontPicker()
        self._preview_font_current = current_preview_font
        self._preview_font_populated = False
        f_row = QFormLayout()
        f_row.setLabelAlignment(Qt.AlignmentFlag.AlignTop)
        f_row.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        f_row.addRow(self.tr("Font family:"), self._preview_font_combo)
        card_lay.addLayout(f_row)
        card_lay.addWidget(self._separator())
        self._preview_font_size = QSpinBox()
        self._preview_font_size.setRange(8, 72)
        self._preview_font_size.setValue(current_preview_font_size)
        card_lay.addLayout(
            self._field_row(self.tr("Font size"), self._preview_font_size)
        )
        prev_lay.addWidget(card)
        prev_lay.addStretch()
        self._stack.addWidget(prev_scroll)

        # ---- Page 4: Storage ----
        stor_scroll, stor_lay = self._build_page(
            self.tr("Storage"),
            self.tr("Configuration paths and session behavior"),
        )
        card, card_lay = self._make_card()

        qs_path = self._app_settings.config_file_path() if self._app_settings else ""
        qs_label = QLabel(qs_path)
        qs_label.setWordWrap(True)
        qs_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        qs_label.setStyleSheet("font-size: 11px; font-family: monospace;")
        info_row = QVBoxLayout()
        info_title = QLabel(self.tr("Config file"))
        info_title.setStyleSheet("font-weight: bold;")
        info_row.addWidget(info_title)
        info_row.addWidget(qs_label)
        card_lay.addLayout(info_row)

        card_lay.addWidget(self._separator())

        self._dotdir_info = QLabel()
        self._dotdir_info.setStyleSheet("font-size: 11px; font-family: monospace;")
        self._dotdir_info.setWordWrap(True)
        info_row2 = QVBoxLayout()
        info_title2 = QLabel(self.tr("Folder data (.cutemd)"))
        info_title2.setStyleSheet("font-weight: bold;")
        info_row2.addWidget(info_title2)
        info_row2.addWidget(self._dotdir_info)
        card_lay.addLayout(info_row2)

        stor_lay.addWidget(card)

        clear_btn = QPushButton(self.tr("Clear last folder"))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_last_folder)
        stor_lay.addWidget(clear_btn)

        stor_lay.addSpacing(12)
        card, card_lay = self._make_card()
        self._session_restore_toggle = ToggleSwitch(current_session_restore_enabled)
        card_lay.addLayout(
            self._field_row(
                self.tr("Restore open tabs on startup"),
                self._session_restore_toggle,
                self.tr("Re-open last session's files"),
            )
        )
        stor_lay.addWidget(card)
        stor_lay.addSpacing(12)

        # Templates directory
        card, card_lay = self._make_card()
        lbl_tmpl = QLabel(self.tr("Templates folder"))
        lbl_tmpl.setStyleSheet("font-size: 12px; font-weight: bold;")
        hint_tmpl = QLabel(self.tr("Markdown files used as templates for new notes"))
        hint_tmpl.setStyleSheet("font-size: 11px;")
        card_lay.addWidget(lbl_tmpl)
        card_lay.addWidget(hint_tmpl)
        tmpl_row = QHBoxLayout()
        self._templates_dir_edit = QLineEdit()
        self._templates_dir_edit.setPlaceholderText(
            self.tr("Select a folder for .md templates…")
        )
        self._templates_dir_edit.setText(current_templates_dir)
        tmpl_row.addWidget(self._templates_dir_edit)
        browse_tmpl = QPushButton("...")
        browse_tmpl.setFixedWidth(40)
        browse_tmpl.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_tmpl.clicked.connect(self._on_browse_templates_dir)
        tmpl_row.addWidget(browse_tmpl)
        card_lay.addLayout(tmpl_row)
        stor_lay.addWidget(card)

        stor_lay.addSpacing(12)

        # Per-folder: attachments directory
        self._attachments_dir_edit: QLineEdit | None = None
        if folder_settings is not None:
            card, card_lay = self._make_card()
            lbl_att = QLabel(self.tr("Attachments folder"))
            lbl_att.setStyleSheet("font-size: 12px; font-weight: bold;")
            hint_att = QLabel(self.tr("Where pasted images are saved"))
            hint_att.setStyleSheet("font-size: 11px;")
            card_lay.addWidget(lbl_att)
            card_lay.addWidget(hint_att)
            att_row = QHBoxLayout()
            self._attachments_dir_edit = QLineEdit()
            val = folder_settings.load().get("attachments_dir", "")
            self._attachments_dir_edit.setText(val)
            self._attachments_dir_edit.setPlaceholderText(
                self.tr("vault root (default)")
            )
            att_row.addWidget(self._attachments_dir_edit)
            browse_att = QPushButton("...")
            browse_att.setFixedWidth(40)
            browse_att.setCursor(Qt.CursorShape.PointingHandCursor)
            browse_att.clicked.connect(self._on_browse_attachments_dir)
            att_row.addWidget(browse_att)
            card_lay.addLayout(att_row)
            stor_lay.addWidget(card)

        stor_lay.addSpacing(12)

        # Daily Note
        card, card_lay = self._make_card()
        lbl_dn = QLabel(self.tr("Daily Note"))
        lbl_dn.setStyleSheet("font-size: 12px; font-weight: bold;")
        card_lay.addWidget(lbl_dn)

        hint_dn = QLabel(
            self.tr("Creates or opens a dated note in the configured folder")
        )
        hint_dn.setStyleSheet("font-size: 11px;")
        card_lay.addWidget(hint_dn)

        # Folder
        dn_folder_lbl = QLabel(self.tr("Folder"))
        dn_folder_lbl.setStyleSheet("font-weight: bold;")
        card_lay.addWidget(dn_folder_lbl)
        dn_folder_row = QHBoxLayout()
        self._daily_folder_edit = QLineEdit()
        self._daily_folder_edit.setText(current_daily_folder)
        self._daily_folder_edit.setPlaceholderText("daily")
        self._daily_folder_edit.setToolTip(
            self.tr("Folder for daily notes, relative to vault root")
        )
        dn_folder_row.addWidget(self._daily_folder_edit)
        browse_dn = QPushButton("...")
        browse_dn.setFixedWidth(40)
        browse_dn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_dn.clicked.connect(self._on_browse_daily_folder)
        dn_folder_row.addWidget(browse_dn)
        card_lay.addLayout(dn_folder_row)

        card_lay.addWidget(self._separator())

        # Template
        lbl_dnt = QLabel(self.tr("Template"))
        lbl_dnt.setStyleSheet("font-weight: bold;")
        card_lay.addWidget(lbl_dnt)
        hint_dnt = QLabel(self.tr("Optional, supports {{date}} and {{title}}"))
        hint_dnt.setStyleSheet("font-size: 11px;")
        card_lay.addWidget(hint_dnt)
        dnt_row = QHBoxLayout()
        self._daily_template_edit = QLineEdit()
        self._daily_template_edit.setText(current_daily_template)
        self._daily_template_edit.setPlaceholderText(self.tr("(optional) path to .md template"))
        dnt_row.addWidget(self._daily_template_edit)
        browse_dnt = QPushButton("...")
        browse_dnt.setFixedWidth(40)
        browse_dnt.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_dnt.clicked.connect(self._on_browse_daily_template)
        dnt_row.addWidget(browse_dnt)
        card_lay.addLayout(dnt_row)

        card_lay.addWidget(self._separator())

        # Date format
        self._daily_date_format_edit = QLineEdit()
        self._daily_date_format_edit.setText(current_daily_date_format)
        self._daily_date_format_edit.setPlaceholderText("%Y-%m-%d")
        card_lay.addLayout(
            self._field_row(
                self.tr("Date format"),
                self._daily_date_format_edit,
                self.tr("Python strftime (default: %Y-%m-%d)"),
            )
        )
        stor_lay.addWidget(card)

        stor_lay.addSpacing(12)

        # Zen Mode
        card, card_lay = self._make_card()
        self._zen_mode_max_width = QSpinBox()
        self._zen_mode_max_width.setRange(300, 3000)
        self._zen_mode_max_width.setSuffix(" px")
        self._zen_mode_max_width.setValue(current_zen_mode_max_width)
        card_lay.addLayout(
            self._field_row(
                self.tr("Zen mode max width"),
                self._zen_mode_max_width,
                self.tr("Maximum editor column width in Zen mode"),
            )
        )
        stor_lay.addWidget(card)

        stor_lay.addSpacing(12)

        # TOC in preview
        card, card_lay = self._make_card()
        self._toc_in_preview_toggle = ToggleSwitch(current_toc_in_preview)
        card_lay.addLayout(
            self._field_row(
                self.tr("Table of Contents in preview"),
                self._toc_in_preview_toggle,
                self.tr("Show an anchor-linked TOC at the top of the preview"),
            )
        )
        stor_lay.addWidget(card)

        stor_lay.addStretch()
        self._stack.addWidget(stor_scroll)

        # ---- Page 5: Shortcuts ----
        sc_scroll, sc_lay = self._build_page(
            self.tr("Shortcuts"),
            self.tr("Customize keyboard shortcuts"),
        )
        if folder_settings is not None:
            current_shortcuts = folder_settings.load_shortcuts()
            self._shortcuts_table = QTableWidget()
            self._shortcuts_table.setColumnCount(3)
            self._shortcuts_table.setHorizontalHeaderLabels(
                [self.tr("Action"), self.tr("Default"), self.tr("Custom")]
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
            sc_lay.addWidget(self._shortcuts_table)
        else:
            sc_lay.addWidget(QLabel(self.tr("Open a folder to customize shortcuts.")))
        sc_lay.addStretch()
        self._stack.addWidget(sc_scroll)

        # ---- Page 6: Sync ----
        sync_scroll, sync_lay = self._build_page(
            self.tr("Sync"),
            self.tr("Connect to a WebDAV server to sync your notes"),
        )
        self._webdav_url_edit: QLineEdit | None = None
        self._webdav_user_edit: QLineEdit | None = None
        self._webdav_pass_edit: QLineEdit | None = None

        if folder_settings is not None:
            card, card_lay = self._make_card()

            self._webdav_url_edit = QLineEdit()
            self._webdav_url_edit.setPlaceholderText(
                self.tr("https://dav.example.com/notes")
            )
            self._webdav_url_edit.setText(current_webdav_url)
            lbl_url = QLabel(self.tr("URL"))
            lbl_url.setStyleSheet("font-size: 12px; font-weight: bold;")
            card_lay.addWidget(lbl_url)
            card_lay.addWidget(self._webdav_url_edit)
            card_lay.addSpacing(8)

            self._webdav_user_edit = QLineEdit()
            self._webdav_user_edit.setPlaceholderText(self.tr("Username"))
            self._webdav_user_edit.setText(current_webdav_user)
            lbl_user = QLabel(self.tr("Username"))
            lbl_user.setStyleSheet("font-size: 12px; font-weight: bold;")
            card_lay.addWidget(lbl_user)
            card_lay.addWidget(self._webdav_user_edit)
            card_lay.addSpacing(8)

            self._webdav_pass_edit = QLineEdit()
            self._webdav_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._webdav_pass_edit.setPlaceholderText(self.tr("Password"))
            self._webdav_pass_edit.setText(current_webdav_pass)
            lbl_pass = QLabel(self.tr("Password"))
            lbl_pass.setStyleSheet("font-size: 12px; font-weight: bold;")
            card_lay.addWidget(lbl_pass)
            card_lay.addWidget(self._webdav_pass_edit)

            card_lay.addSpacing(8)
            self._webdav_backup_edit = QLineEdit()
            self._webdav_backup_edit.setPlaceholderText(
                self.tr("/path/to/backup (required for sync)")
            )
            self._webdav_backup_edit.setText(current_webdav_backup_dir)
            lbl_backup = QLabel(self.tr("Backup directory"))
            lbl_backup.setStyleSheet("font-size: 12px; font-weight: bold;")
            hint = QLabel(self.tr("Vault is copied here before each sync"))
            hint.setStyleSheet("font-size: 11px;")
            card_lay.addWidget(lbl_backup)
            card_lay.addWidget(hint)
            backup_row = QHBoxLayout()
            backup_row.addWidget(self._webdav_backup_edit)
            browse_btn = QPushButton("...")
            browse_btn.setFixedWidth(40)
            browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            browse_btn.clicked.connect(self._on_browse_backup_dir)
            backup_row.addWidget(browse_btn)
            card_lay.addLayout(backup_row)

            card_lay.addSpacing(8)
            test_btn = QPushButton(self.tr("Test Connection"))
            test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            test_btn.clicked.connect(self._on_test_webdav)
            card_lay.addWidget(test_btn)
            self._test_btn = test_btn

            sync_lay.addWidget(card)

            # Auto-sync section
            sync_lay.addWidget(self._section_label(self.tr("AUTOMATIC SYNC")))
            card, card_lay = self._make_card()

            self._auto_sync_toggle = ToggleSwitch(current_auto_sync_enabled)
            card_lay.addLayout(
                self._field_row(
                    self.tr("Auto-sync periodically"),
                    self._auto_sync_toggle,
                    self.tr("Push and pull changes on a schedule"),
                )
            )
            card_lay.addWidget(self._separator())

            self._auto_sync_interval = QSpinBox()
            self._auto_sync_interval.setRange(1, 3600)
            self._auto_sync_interval.setValue(current_auto_sync_interval)
            self._auto_sync_interval.setSuffix(self.tr(" s"))
            self._auto_sync_interval.setToolTip(self.tr("Sync every N seconds"))
            card_lay.addLayout(
                self._field_row(self.tr("Sync interval"), self._auto_sync_interval)
            )
            card_lay.addWidget(self._separator())

            self._sync_on_save_toggle = ToggleSwitch(current_sync_on_save)
            card_lay.addLayout(
                self._field_row(
                    self.tr("Sync on save"),
                    self._sync_on_save_toggle,
                    self.tr("Push immediately when a file is saved"),
                )
            )

            self._auto_sync_toggle.toggled.connect(self._auto_sync_interval.setEnabled)
            self._auto_sync_interval.setEnabled(current_auto_sync_enabled)

            sync_lay.addWidget(card)
        else:
            sync_lay.addWidget(
                QLabel(self.tr("Open a folder to configure WebDAV sync."))
            )
        sync_lay.addStretch()
        self._stack.addWidget(sync_scroll)

        right.addWidget(self._stack, stretch=1)

        # --- Footer ---
        footer = QHBoxLayout()
        footer.setContentsMargins(12, 8, 12, 8)
        self._defaults_btn = QPushButton(self.tr("Defaults"))
        self._defaults_btn.clicked.connect(self._reset_defaults)
        footer.addWidget(self._defaults_btn)
        footer.addStretch()
        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)
        ok_btn = QPushButton(self.tr("Save"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(ok_btn)
        right.addLayout(footer)

        main_layout.addLayout(right)

        # Connect sidebar to stack & reset scroll on page change
        self._section_list.currentRowChanged.connect(self._on_page_changed)
        self._section_list.setCurrentRow(0)

        self._refresh_storage_info()

    # ==================================================================
    # Layout helpers
    # ==================================================================

    def _build_page(
        self, title: str = "", subtitle: str = ""
    ) -> tuple[QScrollArea, QVBoxLayout]:
        """Create a scrollable page with optional header."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(6)

        if title:
            h = QLabel(title)
            h.setStyleSheet("font-weight: bold; font-size: 16px; padding: 0;")
            lay.addWidget(h)
        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet("font-size: 12px; padding: 0 0 8px 0;")
            s.setForegroundRole(s.foregroundRole())
            lay.addWidget(s)

        scroll.setWidget(page)
        return scroll, lay

    def _make_card(self) -> tuple[QFrame, QVBoxLayout]:
        """Create a rounded card frame."""
        frame = QFrame()
        frame.setObjectName("settingsCard")
        frame.setStyleSheet(
            "#settingsCard {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 8px;"
            "  padding: 4px 0px;"
            "}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 4, 16, 4)
        lay.setSpacing(0)
        return frame, lay

    def _field_row(
        self,
        label_text: str,
        control: QWidget,
        hint_text: str | None = None,
    ) -> QHBoxLayout:
        """Create a label | control row, with optional hint below the label."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 8)

        left = QVBoxLayout()
        left.setSpacing(1)
        lbl = QLabel(label_text)
        left.addWidget(lbl)
        if hint_text:
            hint = QLabel(hint_text)
            hint.setStyleSheet("font-size: 11px;")
            left.addWidget(hint)

        row.addLayout(left)
        row.addStretch()
        row.addWidget(control)
        return row

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background: palette(mid); border: none;")
        return line

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "font-size: 10px; font-weight: bold; letter-spacing: 1px;"
            "padding: 12px 0 4px 2px;"
        )
        return lbl

    def _populate_font_picker(self, picker: FontPicker, current: str, families: list[str]) -> None:
        picker._list.clear()
        picker._edit.setPlaceholderText(self.tr("Type to filter\u2026"))
        picker.add_item(self.tr("System"), "System")
        # Batch insert — block repaints while populating the list.
        picker._list.setUpdatesEnabled(False)
        for family in families:
            picker.add_item(family, family)
        picker._list.setUpdatesEnabled(True)
        picker.select_by_data(current if current else "System")

    def _on_page_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if index == 2 and not self._editor_font_populated:
            self._editor_font_populated = True
            self._load_fonts_async(self._editor_font_combo, self._editor_font_current)
        elif index == 3 and not self._preview_font_populated:
            self._preview_font_populated = True
            self._load_fonts_async(self._preview_font_combo, self._preview_font_current)
        # Reset scroll position to top
        scroll = self._stack.widget(index)
        if isinstance(scroll, QScrollArea):
            scroll.verticalScrollBar().setValue(0)

    def _load_fonts_async(self, picker: FontPicker, current: str) -> None:
        global _FONT_FAMILIES
        if _FONT_FAMILIES is not None:
            # Already cached — populate immediately
            self._populate_font_picker(picker, current, _FONT_FAMILIES)
            return
        # Load in background thread, show "System" in the meantime
        picker._edit.setPlaceholderText(self.tr("Loading fonts\u2026"))
        self._font_thread = _FontLoaderThread()
        self._font_thread.result.connect(
            lambda families, p=picker, c=current: self._on_fonts_loaded(p, c, families)
        )
        self._font_thread.start()

    def _on_fonts_loaded(self, picker: FontPicker, current: str, families: list[str]) -> None:
        global _FONT_FAMILIES
        _FONT_FAMILIES = families
        self._populate_font_picker(picker, current, families)

    # ==================================================================
    # Theme swatches
    # ==================================================================

    def _update_theme_swatches(self) -> None:
        hl_color = self.palette().highlight().color().name()
        mid_color = self.palette().mid().color().name()
        for tid, btn in self._theme_swatch_btns:
            theme = get_theme(tid)
            sel = tid == self._selected_theme_id
            if sel:
                border = f"2px solid {hl_color}"
            else:
                border = f"2px solid transparent"
            hover_border = mid_color if not sel else hl_color
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: {theme.base.name()};"
                f"  color: {theme.text.name()};"
                f"  border: {border};"
                f"  border-radius: 8px;"
                f"  font-weight: bold; font-size: 13px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border-color: {hover_border};"
                f"}}"
            )

    def _select_theme(self, theme_id: str) -> None:
        self._selected_theme_id = theme_id
        self._update_theme_swatches()

    # ==================================================================
    # Defaults
    # ==================================================================

    def _reset_defaults(self) -> None:
        self._lang_combo.setCurrentIndex(0)
        # Theme
        for tid, _ in self._theme_swatch_btns:
            if tid == "system":
                self._select_theme(tid)
                break
        # Editor font
        if not self._editor_font_populated:
            self._editor_font_populated = True
            self._load_fonts_async(self._editor_font_combo, self._editor_font_current)
        self._editor_font_combo.select_first()
        self._editor_font_size.setValue(11)
        self._line_number_combo.setCurrentIndex(1)
        self._cursor_width.setValue(2)
        self._link_style_combo.setCurrentIndex(0)
        # Preview font
        if not self._preview_font_populated:
            self._preview_font_populated = True
            self._load_fonts_async(self._preview_font_combo, self._preview_font_current)
        self._preview_font_combo.select_first()
        self._preview_font_size.setValue(16)
        # Toggles
        self._smart_enabled.setChecked(True)
        self._auto_pair_toggle.setChecked(True)
        self._auto_brackets_toggle.setChecked(True)
        self._continue_lists_toggle.setChecked(True)
        self._backspace_pairs_toggle.setChecked(True)
        self._show_hidden_toggle.setChecked(False)
        self._session_restore_toggle.setChecked(False)
        # Autosave
        self._autosave_spin.setValue(5)
        # Attachments
        if self._attachments_dir_edit is not None:
            self._attachments_dir_edit.clear()
        # WebDAV
        if self._webdav_url_edit is not None:
            self._webdav_url_edit.clear()
        if self._webdav_user_edit is not None:
            self._webdav_user_edit.clear()
        if self._webdav_pass_edit is not None:
            self._webdav_pass_edit.clear()
        # Auto-sync
        if hasattr(self, "_auto_sync_toggle"):
            self._auto_sync_toggle.setChecked(False)
        if hasattr(self, "_auto_sync_interval"):
            self._auto_sync_interval.setValue(300)
        if hasattr(self, "_sync_on_save_toggle"):
            self._sync_on_save_toggle.setChecked(False)
        # Shortcuts
        if hasattr(self, "_shortcuts_table"):
            for i in range(self._shortcuts_table.rowCount()):
                editor = self._shortcuts_table.cellWidget(i, 2)
                if isinstance(editor, QKeySequenceEdit):
                    editor.clear()

    # ==================================================================
    # Results (public API — unchanged signatures)
    # ==================================================================

    def selected_theme_id(self) -> str:
        return self._selected_theme_id

    def selected_editor_font(self) -> str:
        if not self._editor_font_populated:
            return self._editor_font_current
        return self._editor_font_combo.current_data()

    def selected_editor_font_size(self) -> int:
        return self._editor_font_size.value()

    def selected_preview_font(self) -> str:
        if not self._preview_font_populated:
            return self._preview_font_current
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
            "auto_pair": self._auto_pair_toggle.isChecked(),
            "auto_pair_brackets": self._auto_brackets_toggle.isChecked(),
            "continue_lists": self._continue_lists_toggle.isChecked(),
            "backspace_pairs": self._backspace_pairs_toggle.isChecked(),
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

    def selected_attachments_dir(self) -> str | None:
        if self._attachments_dir_edit is not None:
            return self._attachments_dir_edit.text().strip() or None
        return None

    def selected_autosave_interval(self) -> int:
        return self._autosave_spin.value()

    def selected_auto_update_check(self) -> bool:
        return self._auto_update_toggle.isChecked()

    def selected_menu_bar_visible(self) -> bool:
        return self._menu_bar_toggle.isChecked()

    def selected_auto_sync_enabled(self) -> bool:
        if hasattr(self, "_auto_sync_toggle"):
            return self._auto_sync_toggle.isChecked()
        return False

    def selected_auto_sync_interval(self) -> int:
        if hasattr(self, "_auto_sync_interval"):
            return self._auto_sync_interval.value()
        return 300

    def selected_sync_on_save(self) -> bool:
        if hasattr(self, "_sync_on_save_toggle"):
            return self._sync_on_save_toggle.isChecked()
        return False

    def selected_session_restore_enabled(self) -> bool:
        return self._session_restore_toggle.isChecked()

    def selected_show_hidden_files(self) -> bool:
        return self._show_hidden_toggle.isChecked()

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

    def selected_webdav_backup_dir(self) -> str:
        if hasattr(self, "_webdav_backup_edit") and self._webdav_backup_edit is not None:
            return self._webdav_backup_edit.text().strip()
        return ""

    def selected_templates_dir(self) -> str:
        if hasattr(self, "_templates_dir_edit") and self._templates_dir_edit is not None:
            return self._templates_dir_edit.text().strip()
        return ""

    def selected_daily_folder(self) -> str:
        if hasattr(self, "_daily_folder_edit") and self._daily_folder_edit is not None:
            return self._daily_folder_edit.text().strip()
        return "daily"

    def selected_daily_template(self) -> str:
        if hasattr(self, "_daily_template_edit") and self._daily_template_edit is not None:
            return self._daily_template_edit.text().strip()
        return ""

    def selected_daily_date_format(self) -> str:
        if hasattr(self, "_daily_date_format_edit") and self._daily_date_format_edit is not None:
            return self._daily_date_format_edit.text().strip()
        return "%Y-%m-%d"

    def selected_zen_mode_max_width(self) -> int:
        if hasattr(self, "_zen_mode_max_width") and self._zen_mode_max_width is not None:
            return self._zen_mode_max_width.value()
        return 800

    def selected_toc_in_preview(self) -> bool:
        if hasattr(self, "_toc_in_preview_toggle") and self._toc_in_preview_toggle is not None:
            return self._toc_in_preview_toggle.isChecked()
        return False

    def selected_spell_check_langs(self) -> str:
        if hasattr(self, "_spell_check_lang_cbs"):
            checked = [k for k, cb in self._spell_check_lang_cbs.items() if cb.isChecked()]
            return ",".join(checked)
        return ""

    # ==================================================================
    # Storage
    # ==================================================================

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
        if self._app_settings is not None:
            self._app_settings.remove_last_folder()
            self._app_settings.remove_recent_folders()
        QMessageBox.information(
            self,
            self.tr("Storage"),
            self.tr(
                "Last folder and recent folders list cleared.\n"
                "You will be prompted to choose a folder on next launch."
            ),
        )

    # ==================================================================
    # Sync helpers
    # ==================================================================

    def _on_browse_backup_dir(self) -> None:
        """Open a directory picker for the backup directory."""
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select backup directory"),
            self._webdav_backup_edit.text() or str(Path.home()),
        )
        if path:
            self._webdav_backup_edit.setText(path)

    def _on_browse_templates_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        cur = self._templates_dir_edit.text().strip() if self._templates_dir_edit else ""
        if cur and self._current_folder and not Path(cur).is_absolute():
            cur = str(Path(self._current_folder) / cur)
        start_dir = cur or self._current_folder or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select templates folder"), start_dir,
        )
        if path:
            # Show relative path when inside the open folder.
            if self._current_folder:
                try:
                    path = str(Path(path).resolve().relative_to(self._current_folder))
                except (ValueError, OSError):
                    pass
            self._templates_dir_edit.setText(path)

    def _on_browse_attachments_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        # Resolve current value for start dir.
        cur = self._attachments_dir_edit.text().strip() if self._attachments_dir_edit else ""
        if cur and self._current_folder and not Path(cur).is_absolute():
            cur = str(Path(self._current_folder) / cur)
        start_dir = cur or self._current_folder or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select attachments folder"), start_dir,
        )
        if path:
            if self._current_folder:
                try:
                    path = str(Path(path).resolve().relative_to(self._current_folder))
                except (ValueError, OSError):
                    pass
            self._attachments_dir_edit.setText(path)

    def _on_browse_daily_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        cur = self._daily_folder_edit.text().strip() if hasattr(self, "_daily_folder_edit") else ""
        if cur and self._current_folder and not Path(cur).is_absolute():
            cur = str(Path(self._current_folder) / cur)
        start_dir = cur or self._current_folder or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select daily notes folder"), start_dir,
        )
        if path:
            if self._current_folder:
                try:
                    path = str(Path(path).resolve().relative_to(self._current_folder))
                except (ValueError, OSError):
                    pass
            self._daily_folder_edit.setText(path)

    def _on_browse_daily_template(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        # Start from templates folder, or vault root.
        start = (
            self._templates_dir_edit.text().strip() if hasattr(self, "_templates_dir_edit") and self._templates_dir_edit.text().strip() else ""
        )
        if start and self._current_folder and not Path(start).is_absolute():
            start = str(Path(self._current_folder) / start)
        start = start or self._current_folder or str(Path.home())

        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select daily note template"), start,
            self.tr("Markdown files (*.md);;All files (*)"),
        )
        if path:
            if self._current_folder:
                try:
                    path = str(Path(path).resolve().relative_to(self._current_folder))
                except (ValueError, OSError):
                    pass
            self._daily_template_edit.setText(path)

    def _on_test_webdav(self) -> None:
        url = self._webdav_url_edit.text().strip() if self._webdav_url_edit else ""
        user = self._webdav_user_edit.text().strip() if self._webdav_user_edit else ""
        pw = self._webdav_pass_edit.text() if self._webdav_pass_edit else ""

        if not url:
            QMessageBox.warning(
                self, self.tr("Test Connection"), self.tr("Please enter a URL.")
            )
            return

        self._test_btn.setEnabled(False)
        self._test_btn.setText(self.tr("Testing\u2026"))

        worker = _WebDAVTestWorker(url, user, pw)
        worker.result.connect(self._on_test_result)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self._test_worker = worker

    def _on_test_result(self, ok: bool, err: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_btn.setText(self.tr("Test Connection"))
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

    # ==================================================================
    # Dictionary download
    # ==================================================================

    def _on_install_dict(self, hunspell_code: str) -> None:
        from core.dict_manager import AVAILABLE_DICTS, DictDownloader

        ui_code = next(k for k, v in AVAILABLE_DICTS.items() if v == hunspell_code)
        self._dict_buttons[hunspell_code].setEnabled(False)
        self._dict_buttons[hunspell_code].setText(self.tr("Downloading…"))
        self._dict_status_labels[hunspell_code].setText(
            "\u23f3 " + ui_code.upper() + " (" + hunspell_code + ")"
        )

        self._downloader = DictDownloader(ui_code, hunspell_code, self)
        self._downloader.finished.connect(
            lambda ok, err: self._on_dict_downloaded(hunspell_code, ok, err)
        )
        self._downloader.start()

    def _on_uninstall_dict(self, hunspell_code: str) -> None:
        from core.dict_manager import AVAILABLE_DICTS, uninstall_dict

        uninstall_dict(hunspell_code)
        ui_code = next(k for k, v in AVAILABLE_DICTS.items() if v == hunspell_code)
        self._dict_status_labels[hunspell_code].setText(
            "\u2b1c " + ui_code.upper() + " (" + hunspell_code + ")"
        )
        self._dict_buttons[hunspell_code].setText(self.tr("Install"))
        self._dict_buttons[hunspell_code].clicked.disconnect()
        self._dict_buttons[hunspell_code].clicked.connect(
            lambda checked, c=hunspell_code: self._on_install_dict(c)
        )

    def _on_dict_downloaded(self, hunspell_code: str, ok: bool, err: str) -> None:
        from core.dict_manager import AVAILABLE_DICTS

        ui_code = next(k for k, v in AVAILABLE_DICTS.items() if v == hunspell_code)
        if ok:
            self._dict_status_labels[hunspell_code].setText(
                "\u2705 " + ui_code.upper() + " (" + hunspell_code + ")"
            )
            self._dict_buttons[hunspell_code].setText(self.tr("Uninstall"))
            self._dict_buttons[hunspell_code].clicked.disconnect()
            self._dict_buttons[hunspell_code].clicked.connect(
                lambda checked, c=hunspell_code: self._on_uninstall_dict(c)
            )
            # Add to language checkboxes if not already there
            if hasattr(self, "_spell_check_lang_cbs") and hunspell_code not in self._spell_check_lang_cbs:
                ui_code = next(k for k, v in AVAILABLE_DICTS.items() if v == hunspell_code)
                cb = QCheckBox(f"{ui_code} ({hunspell_code})")
                self._spell_check_lang_cbs[hunspell_code] = cb
                # Find the dictionaries card and add the row
                pass  # Too complex — just refresh on next open
        else:
            self._dict_status_labels[hunspell_code].setText(
                "\u274c " + ui_code.upper() + " (" + hunspell_code + ")"
            )
            self._dict_buttons[hunspell_code].setText(self.tr("Install"))
        self._dict_buttons[hunspell_code].setEnabled(True)
