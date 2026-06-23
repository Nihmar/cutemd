"""Welcome dialog shown on first launch with no previous folder."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WelcomeDialog(QDialog):
    """Modal dialog offering folder selection or blank edit mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Welcome to CuteMD"))
        self.setMinimumWidth(420)
        self._selected_folder: Path | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(self.tr("CuteMD \u2013 Markdown Editor"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        subtitle = QLabel(
            self.tr("Choose a folder to manage your notes, or start editing a single file.")
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        open_btn = QPushButton(self.tr("&Open Folder\u2026"))
        open_btn.setMinimumHeight(36)
        open_btn.clicked.connect(self._choose_folder)
        layout.addWidget(open_btn)

        new_btn = QPushButton(self.tr("&New File"))
        new_btn.setMinimumHeight(36)
        new_btn.clicked.connect(self._start_edit_mode)
        layout.addWidget(new_btn)

        recent_folders = self._load_recent_folders()
        if recent_folders:
            layout.addSpacing(6)
            recent_label = QLabel(self.tr("Recent folders:"))
            layout.addWidget(recent_label)

            self._recent_list = QListWidget()
            self._recent_list.setMaximumHeight(120)
            for rf in recent_folders:
                item = QListWidgetItem(rf)
                item.setData(Qt.ItemDataRole.UserRole, rf)
                self._recent_list.addItem(item)
            self._recent_list.itemDoubleClicked.connect(self._on_recent_selected)
            layout.addWidget(self._recent_list)

        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_folder(self) -> Path | None:
        return self._selected_folder

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
