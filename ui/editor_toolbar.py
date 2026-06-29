"""Editor formatting toolbar — buttons for Markdown syntax insertion."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QMenu, QSizePolicy, QToolButton, QWidget

from core.markdown_actions import HEADING_PREFIXES, TOOLBAR_ITEMS


class EditorToolbar(QWidget):
    """Toolbar with heading menu and formatting buttons."""

    format_requested = Signal(str)   # syntax to insert
    image_requested = Signal()
    toggle_search = Signal()         # toggles the find bar
    detach_preview = Signal()        # detach/reattach the preview pane
    insert_table_requested = Signal()  # open insert-table dialog

    def __init__(
        self,
        icon_color: QColor,
        make_icon: Callable[[str, QColor, int], QIcon],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("editorToolbar")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self._icon_color = icon_color
        self._make_icon = make_icon
        self._buttons: list[tuple[QToolButton, str]] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
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
            if icon_name == "table":
                b.clicked.connect(self.insert_table_requested.emit)
            else:
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

        search_btn = QToolButton()
        search_btn.setIcon(self._icon("search"))
        search_btn.setToolTip(self.tr("Find in page"))
        search_btn.setAutoRaise(True)
        search_btn.setIconSize(QSize(18, 18))
        search_btn.setFixedSize(30, 28)
        search_btn.clicked.connect(self.toggle_search)
        layout.addWidget(search_btn)
        self._buttons.append((search_btn, "search"))

        detach_btn = QToolButton()
        detach_btn.setIcon(self._icon("detach"))
        detach_btn.setToolTip(self.tr("Detach preview"))
        detach_btn.setAutoRaise(True)
        detach_btn.setCheckable(True)
        detach_btn.setIconSize(QSize(18, 18))
        detach_btn.setFixedSize(30, 28)
        detach_btn.clicked.connect(self.detach_preview)
        layout.addWidget(detach_btn)
        self._detach_btn = detach_btn
        self._buttons.append((detach_btn, "detach"))

        layout.addStretch()

    def recolor(self, icon_color: QColor) -> None:
        self._icon_color = icon_color
        self._heading_btn.setIcon(self._icon("heading"))
        for btn, name in self._buttons:
            btn.setIcon(self._icon(name))

    def retranslate(self) -> None:
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
