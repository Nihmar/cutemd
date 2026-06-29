"""Template picker dialog — select a template for new notes."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidgetItem,
    QVBoxLayout,
)

from ui.widgets import CuteListWidget


class TemplatePicker(QDialog):
    """A popup dialog listing available Markdown templates plus a Blank option.

    On selection the dialog closes and the result is available via
    ``selected_path`` (None for Blank, a Path for a template file).
    """

    def __init__(
        self,
        templates_dir: Path | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("New from template"))
        self.setMinimumWidth(360)
        self.selected_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = CuteListWidget()
        self._list.setSpacing(4)

        # Blank (no template) — always first
        blank_item = QListWidgetItem(self.tr("Blank"))
        blank_item.setData(Qt.ItemDataRole.UserRole, None)
        font = blank_item.font()
        font.setBold(True)
        blank_item.setFont(font)
        self._list.addItem(blank_item)

        # Template files from the configured folder
        if templates_dir is not None and templates_dir.is_dir():
            tpl_files = sorted(
                templates_dir.glob("*.md"),
                key=lambda p: p.stem.lower(),
            )
            if tpl_files:
                sep = QListWidgetItem(self.tr("── Templates ──"))
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                sep.setForeground(Qt.GlobalColor.gray)
                self._list.addItem(sep)

                for fpath in tpl_files:
                    item = QListWidgetItem(fpath.stem)
                    item.setData(Qt.ItemDataRole.UserRole, str(fpath))
                    item.setToolTip(str(fpath))
                    self._list.addItem(item)
            else:
                hint = QListWidgetItem(
                    self.tr("(no .md files in templates folder)")
                )
                hint.setFlags(Qt.ItemFlag.NoItemFlags)
                self._list.addItem(hint)

        layout.addWidget(self._list)

        # Footer hint
        hint_label = QLabel(
            self.tr("Esc to cancel  ·  Enter to confirm")
        )
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet(
            "color: #888; font-size: 11px; padding: 6px;"
        )
        layout.addWidget(hint_label)

        self._list.setCurrentRow(0)
        self._list.itemActivated.connect(self._on_accept)

        # Enter / Escape shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(
            self._on_accept
        )
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(
            self._on_accept
        )
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            self.reject
        )

    def _on_accept(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            raw = item.data(Qt.ItemDataRole.UserRole)
            self.selected_path = Path(raw) if raw else None
        else:
            self.selected_path = None

        # Defer accept so the activated signal doesn't cause issues
        QTimer.singleShot(0, self.accept)

    # ------------------------------------------------------------------
    # Template content resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_content(template_path: Path | None, title: str = "") -> str:
        """Return the resolved content for *template_path*.

        If None returns an empty string.  Substitutes ``{{date}}`` and
        ``{{title}}`` placeholders.
        """
        if template_path is None:
            return ""

        try:
            text = template_path.read_text(encoding="utf-8")
        except OSError:
            return ""

        today = date.today().isoformat()
        text = text.replace("{{date}}", today).replace("{{title}}", title)
        return text
