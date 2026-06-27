"""Editor formatting toolbar — buttons for Markdown syntax insertion."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QMenu, QToolButton, QWidget

from core.markdown_actions import HEADING_PREFIXES, TOOLBAR_ITEMS


class EditorToolbar(QWidget):
    """Toolbar with heading menu, formatting buttons, and panel toggles."""

    format_requested = Signal(str)   # syntax to insert
    image_requested = Signal()
    toggle_right_panel = Signal()    # toggles TOC/backlinks right dock

    def __init__(
        self,
        icon_color: QColor,
        make_icon: Callable[[str, QColor, int], QIcon],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("editorToolbar")

        self._icon_color = icon_color
        self._make_icon = make_icon
        self._buttons: list[tuple[QToolButton, str]] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        # --- Heading button ---
        self._heading_btn = QToolButton()
        self._heading_btn.setIcon(self._icon("heading"))
        self._heading_btn.setToolTip(self.tr("Heading level"))
        self._heading_btn.setAutoRaise(True)
        self._heading_btn.setIconSize(QSize(18, 18))
        self._heading_btn.setFixedSize(30, 28)
        self._heading_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        heading_menu = QMenu(self._heading_btn)
        for prefix, label in HEADING_PREFIXES:
            level = len(prefix.strip())
            icon_size = max(8, 20 - level * 2)
            action = heading_menu.addAction(self.tr(label))
            action.setIcon(self._icon("heading", icon_size))
            action.triggered.connect(lambda checked=False, p=prefix: self.format_requested.emit(p))
        self._heading_btn.setMenu(heading_menu)
        layout.addWidget(self._heading_btn)

        self._add_separator(layout)

        # --- Toolbar buttons ---
        for icon_name, syntax, _tip_key in TOOLBAR_ITEMS:
            b = QToolButton()
            b.setIcon(self._icon(icon_name))
            b.setToolTip(self.tr(_tip_key))
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            b.setFixedSize(30, 28)
            b.clicked.connect(lambda checked=False, s=syntax: self.format_requested.emit(s))
            layout.addWidget(b)
            self._buttons.append((b, icon_name))

            # Separators after specific groups
            if icon_name == "list-task":
                self._add_separator(layout)
            elif icon_name == "hr":
                self._add_separator(layout)
            elif icon_name == "code":
                self._add_separator(layout)

        # --- Image button ---
        img_btn = QToolButton()
        img_btn.setIcon(self._icon("image"))
        img_btn.setToolTip(self.tr("Insert image"))
        img_btn.setAutoRaise(True)
        img_btn.setIconSize(QSize(18, 18))
        img_btn.setFixedSize(30, 28)
        img_btn.clicked.connect(self.image_requested)
        layout.addWidget(img_btn)
        self._buttons.append((img_btn, "image"))

        self._add_separator(layout)

        # --- TOC / right panel toggle ---
        self._toc_btn = QToolButton()
        self._toc_btn.setIcon(self._icon("toc"))
        self._toc_btn.setToolTip(self.tr("Toggle Table of Contents"))
        self._toc_btn.setAutoRaise(True)
        self._toc_btn.setCheckable(True)
        self._toc_btn.setIconSize(QSize(18, 18))
        self._toc_btn.setFixedSize(30, 28)
        self._toc_btn.clicked.connect(self.toggle_right_panel)
        layout.addWidget(self._toc_btn)
        self._buttons.append((self._toc_btn, "toc"))

        layout.addStretch()

    def recolor(self, icon_color: QColor) -> None:
        self._icon_color = icon_color
        self._heading_btn.setIcon(self._icon("heading"))
        for btn, name in self._buttons:
            btn.setIcon(self._icon(name))

    def set_toc_checked(self, checked: bool) -> None:
        """Update the TOC button checked state (from external toggle)."""
        if hasattr(self, "_toc_btn"):
            self._toc_btn.setChecked(checked)
        self._heading_btn.setToolTip(self.tr("Heading level"))
        for (btn, _), (_icon, _syntax, tip_key) in zip(self._buttons, TOOLBAR_ITEMS):
            btn.setToolTip(self.tr(tip_key))
        if self._buttons:
            self._buttons[-1][0].setToolTip(self.tr("Insert image"))

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _icon(self, name: str, size: int = 18) -> QIcon:
        return self._make_icon(name, self._icon_color, size)

    @staticmethod
    def _add_separator(layout: QHBoxLayout) -> None:
        s = QWidget()
        s.setObjectName("toolbarSep")
        s.setFixedWidth(1)
        layout.addWidget(s)
