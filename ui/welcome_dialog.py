"""Welcome dialog shown on first launch with no previous folder."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import CuteListWidget

# Only layout, typography and structural chrome — every colour is a
# palette() reference so the stylesheet adapts to whatever theme is active.
_STYLESHEET = """
QLabel#badge {
    color: palette(highlight);
    background-color: palette(alternate-base);
    border: 1px solid palette(midlight);
    border-radius: 4px;
    font-family: monospace;
    font-size: 12px;
    padding: 3px 10px;
}
QLabel#title {
    font-size: 20px;
    font-weight: bold;
}
QLabel#subtitle {
    color: palette(mid);
    font-size: 13px;
}
QLabel#sectionLabel {
    color: palette(mid);
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}
"""


class _FolderDelegate(QStyledItemDelegate):
    """Palette-aware two-line item delegate: folder name + truncated path.

    Draws the standard Fusion background (CE_ItemViewItem) so hover and
    selection states come from the active theme automatically.  Text colours
    switch to HighlightedText when the item is hovered or selected, mirroring
    the QListWidget::item:hover rule in style.qss.
    """

    _ITEM_H = 52
    _EMPTY_H = 48
    _H_PAD = 14
    _GAP = 3
    _NAME_PT = 13
    _PATH_PT = 11

    def sizeHint(self, option, index):
        h = self._ITEM_H if index.data(Qt.ItemDataRole.UserRole) else self._EMPTY_H
        return QSize(option.rect.width(), h)

    def paint(self, painter, option, index):
        # Let Fusion draw the item background (highlight on hover/select)
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget
        )

        folder_path = index.data(Qt.ItemDataRole.UserRole)

        # ── Empty state ────────────────────────────────────────────
        if not folder_path:
            painter.save()
            f = QFont(option.font)
            f.setPointSize(self._PATH_PT)
            f.setItalic(True)
            painter.setFont(f)
            painter.setPen(option.palette.color(QPalette.ColorRole.Mid))
            painter.drawText(
                option.rect, Qt.AlignmentFlag.AlignCenter, "No recent folders yet"
            )
            painter.restore()
            return

        # ── Folder item ────────────────────────────────────────────
        path = Path(folder_path)
        display_name = path.name or str(path)
        path_str = str(path)
        if len(path_str) > 52:
            path_str = "\u2026" + path_str[-50:]

        is_active = bool(
            option.state
            & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver)
        )
        if is_active:
            fg = option.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText
            )
            name_color = path_color = fg
        else:
            name_color = option.palette.color(QPalette.ColorRole.Text)
            path_color = option.palette.color(QPalette.ColorRole.Mid)

        name_font = QFont(option.font)
        name_font.setPointSize(self._NAME_PT)
        name_font.setBold(True)
        name_h = QFontMetrics(name_font).height()

        path_font = QFont(option.font)
        path_font.setPointSize(self._PATH_PT)
        path_h = QFontMetrics(path_font).height()

        r = option.rect
        y = r.y() + (r.height() - name_h - self._GAP - path_h) // 2

        painter.save()

        painter.setFont(name_font)
        painter.setPen(name_color)
        painter.drawText(
            r.x() + self._H_PAD,
            y,
            r.width() - 2 * self._H_PAD,
            name_h,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            display_name,
        )

        painter.setFont(path_font)
        painter.setPen(path_color)
        painter.drawText(
            r.x() + self._H_PAD,
            y + name_h + self._GAP,
            r.width() - 2 * self._H_PAD,
            path_h,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            path_str,
        )

        painter.restore()


class WelcomeDialog(QDialog):
    """Modal dialog offering folder selection or blank edit mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Welcome to CuteMD"))
        self.setMinimumWidth(440)
        self.setMinimumHeight(500)
        self._selected_folder: Path | None = None
        self.setStyleSheet(_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 20)
        layout.setSpacing(0)

        # ── Badge ─────────────────────────────────────────────────────
        # badge_row = QHBoxLayout()
        # badge = QLabel(self.tr("# markdown editor"))
        # badge.setObjectName("badge")
        # badge_row.addWidget(badge)
        # badge_row.addStretch()
        # layout.addLayout(badge_row)

        # layout.addSpacing(16)

        # ── Title ─────────────────────────────────────────────────────
        title = QLabel(self.tr("CuteMD"))
        title.setObjectName("title")
        layout.addWidget(title)

        layout.addSpacing(6)

        # ── Subtitle ──────────────────────────────────────────────────
        subtitle = QLabel(
            self.tr("Open a folder to manage your notes, or start with a blank file.")
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(28)

        # ── Primary action ────────────────────────────────────────────
        open_btn = QPushButton(self.tr("&Open Folder\u2026"))
        open_btn.setObjectName("primaryBtn")
        open_btn.clicked.connect(self._choose_folder)
        layout.addWidget(open_btn)

        layout.addSpacing(8)

        # ── Secondary action ──────────────────────────────────────────
        new_btn = QPushButton(self.tr("&New File"))
        new_btn.setObjectName("secondaryBtn")
        new_btn.clicked.connect(self._start_edit_mode)
        layout.addWidget(new_btn)

        layout.addSpacing(24)

        # ── Divider ───────────────────────────────────────────────────
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: palette(midlight);")
        layout.addWidget(divider)

        layout.addSpacing(18)

        # ── Section label ─────────────────────────────────────────────
        section_label = QLabel(self.tr("RECENT FOLDERS"))
        section_label.setObjectName("sectionLabel")
        layout.addWidget(section_label)

        layout.addSpacing(8)

        # ── Recent list ───────────────────────────────────────────────
        self._recent_list = CuteListWidget()
        self._recent_list.setMaximumHeight(160)
        self._recent_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._recent_list.setItemDelegate(_FolderDelegate(self._recent_list))
        self._recent_list.viewport().setMouseTracking(True)

        recent_folders = self._load_recent_folders()
        if recent_folders:
            for rf in recent_folders:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, rf)
                self._recent_list.addItem(item)
            # itemActivated fires on both double-click and Return/Enter
            self._recent_list.itemActivated.connect(self._on_recent_selected)
        else:
            empty_item = QListWidgetItem()
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._recent_list.addItem(empty_item)

        layout.addWidget(self._recent_list)
        layout.addStretch()

        # ── Close ─────────────────────────────────────────────────────
        close_btn = QPushButton(self.tr("Close"))
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def selected_folder(self) -> Path | None:
        return self._selected_folder

    # ──────────────────────────────────────────────────────────────────
    # Private slots
    # ──────────────────────────────────────────────────────────────────

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr("Open Folder"), "")
        if folder:
            self._selected_folder = Path(folder)
            self.accept()

    def _start_edit_mode(self) -> None:
        self._selected_folder = None
        self.accept()

    def _on_recent_selected(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).is_dir():
            self._selected_folder = Path(path)
            self.accept()

    # ──────────────────────────────────────────────────────────────────
    # Settings
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_recent_folders() -> list[str]:
        from PySide6.QtCore import QSettings

        settings = QSettings("cutemd", "cutemd")
        recent = settings.value("recent_folders", [])
        if isinstance(recent, str):
            recent = [recent] if recent else []
        if not isinstance(recent, list):
            return []
        return [p for p in recent if Path(p).is_dir()]
