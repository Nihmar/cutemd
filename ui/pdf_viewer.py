"""Embedded PDF viewer using QPdfDocument."""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PdfViewer(QWidget):
    """Paginated PDF viewer with navigation bar and zoom."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: QPdfDocument | None = None
        self._path: Path | None = None
        self._page = 0
        self._zoom = 1.0
        self._page_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        nav = QHBoxLayout()
        self._prev_btn = QPushButton("\u25c0")
        self._prev_btn.setFixedWidth(32)
        self._page_label = QLabel("0 / 0")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._next_btn = QPushButton("\u25b6")
        self._next_btn.setFixedWidth(32)
        self._open_btn = QPushButton(self.tr("Open externally"))
        nav.addStretch()
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._page_label)
        nav.addWidget(self._next_btn)
        nav.addSpacing(10)
        nav.addWidget(self._open_btn)
        nav.addStretch()
        nav_widget = QWidget()
        nav_widget.setLayout(nav)

        self._page_view = QLabel()
        self._page_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._page_view)
        self._scroll.viewport().installEventFilter(self)

        layout.addWidget(nav_widget)
        layout.addWidget(self._scroll)

        self._prev_btn.clicked.connect(self._prev_page)
        self._next_btn.clicked.connect(self._next_page)
        self._open_btn.clicked.connect(self._open_externally)

    def load(self, path: Path) -> None:
        self._path = path.resolve()
        self._doc = QPdfDocument()
        self._doc.load(str(self._path))
        self._page = 0
        self._zoom = 1.0
        self._page_count = max(self._doc.pageCount(), 0)
        self._render()

    def _render(self) -> None:
        if self._page_count == 0:
            self._page_view.setText(self.tr("Cannot render this PDF."))
            self._page_label.setText("0 / 0")
            return
        size = self._scroll.viewport().size() * self._zoom
        img = self._doc.render(self._page, QSize(int(size.width()), int(size.height())))
        self._page_view.setPixmap(QPixmap.fromImage(img))
        self._page_label.setText(f"{self._page + 1} / {self._page_count}")
        self._prev_btn.setEnabled(self._page > 0)
        self._next_btn.setEnabled(self._page < self._page_count - 1)

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render()

    def _next_page(self) -> None:
        if self._page < self._page_count - 1:
            self._page += 1
            self._render()

    def _open_externally(self) -> None:
        if self._path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))

    @property
    def page_count(self) -> int:
        return self._page_count

    def zoom_in(self) -> None:
        self._zoom = min(5.0, self._zoom * 1.2)
        self._render()

    def zoom_out(self) -> None:
        self._zoom = max(0.1, self._zoom / 1.2)
        self._render()

    def eventFilter(self, obj: object, event) -> bool:
        if obj is self._scroll.viewport():
            if event.type() == event.Type.Resize:
                self._render()
                return False
            if event.type() == event.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    delta = event.angleDelta().y() / 120.0
                    self._zoom = max(0.1, min(10.0, self._zoom + delta * 0.15))
                    self._render()
                    return True
        return super().eventFilter(obj, event)
