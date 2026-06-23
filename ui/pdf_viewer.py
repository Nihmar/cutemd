"""Embedded PDF viewer using QPdfDocument — scroll-to-page, fit-width/height, zoom."""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PdfViewer(QWidget):
    """Paginated PDF viewer with navigation, zoom, fit-width, fit-height."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: QPdfDocument | None = None
        self._path: Path | None = None
        self._page = 0
        self._zoom = 1.0
        self._page_count = 0
        self._fit_width = True
        self._fit_height = False
        self._changing_page = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        nav = QHBoxLayout()
        self._prev_btn = QPushButton("\u25c0")
        self._prev_btn.setFixedWidth(32)
        self._page_label = QLabel("0 / 0")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._next_btn = QPushButton("\u25b6")
        self._next_btn.setFixedWidth(32)

        self._fit_width_cb = QCheckBox(self.tr("Fit width"))
        self._fit_width_cb.setChecked(True)
        self._fit_height_cb = QCheckBox(self.tr("Fit height"))
        # Make checkboxes mutually exclusive
        self._fit_group = QButtonGroup(self)
        self._fit_group.addButton(self._fit_width_cb)
        self._fit_group.addButton(self._fit_height_cb)
        self._fit_group.setExclusive(False)
        self._fit_width_cb.toggled.connect(self._on_fit_mode_changed)
        self._fit_height_cb.toggled.connect(self._on_fit_mode_changed)

        self._open_btn = QPushButton(self.tr("Open externally"))
        nav.addStretch()
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._page_label)
        nav.addWidget(self._next_btn)
        nav.addSpacing(10)
        nav.addWidget(self._fit_width_cb)
        nav.addWidget(self._fit_height_cb)
        nav.addSpacing(6)
        nav.addWidget(self._open_btn)
        nav.addStretch()
        nav_widget = QWidget()
        nav_widget.setLayout(nav)

        self._page_view = QLabel()
        self._page_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_view.setStyleSheet("background: white;")
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
        if self._page_count == 0:
            self._page_view.setText(self.tr("Cannot render this PDF."))
            self._page_label.setText("0 / 0")
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            return
        self._render()

    def _render(self) -> None:
        if self._doc is None or self._page_count == 0:
            return
        page_size = self._doc.pagePointSize(self._page)
        if page_size.width() <= 0:
            return
        vp = self._scroll.viewport()
        vp_w = max(vp.width(), 100)
        vp_h = max(vp.height(), 100)
        aspect = page_size.height() / page_size.width()

        if self._fit_width and self._fit_height:
            scale = min(vp_w / page_size.width(), vp_h / page_size.height())
            render_w = int(page_size.width() * scale)
            render_h = int(page_size.height() * scale)
        elif self._fit_width:
            render_w = int(vp_w)
            render_h = int(vp_w * aspect)
        elif self._fit_height:
            render_h = int(vp_h)
            render_w = int(vp_h / aspect) if aspect > 0 else 1
        else:
            render_w = max(int(vp_w * self._zoom), 1)
            render_h = int(render_w * aspect)

        img = self._doc.render(self._page, QSize(render_w, render_h))
        self._page_view.setPixmap(QPixmap.fromImage(img))
        self._page_label.setText(f"{self._page + 1} / {self._page_count}")
        self._prev_btn.setEnabled(self._page > 0)
        self._next_btn.setEnabled(self._page < self._page_count - 1)

        # Reset scroll to top after pixmap is laid out
        if self._changing_page:
            QTimer.singleShot(0, self._reset_scroll)
        self._changing_page = False

    def _reset_scroll(self) -> None:
        self._scroll.verticalScrollBar().setValue(0)
        self._scroll.horizontalScrollBar().setValue(0)

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._changing_page = True
            self._render()

    def _next_page(self) -> None:
        if self._page < self._page_count - 1:
            self._page += 1
            self._changing_page = True
            self._render()

    def _open_externally(self) -> None:
        if self._path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))

    def _on_fit_mode_changed(self) -> None:
        # Enforce mutual exclusivity: uncheck the other when one is checked
        if self._fit_width_cb.isChecked() and self._fit_height_cb.isChecked():
            # Both can't be on — uncheck the one that was just toggled
            sender = self.sender()
            if sender is self._fit_width_cb:
                self._fit_height_cb.blockSignals(True)
                self._fit_height_cb.setChecked(False)
                self._fit_height_cb.blockSignals(False)
            else:
                self._fit_width_cb.blockSignals(True)
                self._fit_width_cb.setChecked(False)
                self._fit_width_cb.blockSignals(False)
        self._fit_width = self._fit_width_cb.isChecked()
        self._fit_height = self._fit_height_cb.isChecked()
        if not self._fit_width and not self._fit_height:
            self._zoom = 1.0
        self._render()

    @property
    def page_count(self) -> int:
        return self._page_count

    def zoom_in(self) -> None:
        self._fit_width_cb.blockSignals(True)
        self._fit_height_cb.blockSignals(True)
        self._fit_width_cb.setChecked(False)
        self._fit_height_cb.setChecked(False)
        self._fit_width_cb.blockSignals(False)
        self._fit_height_cb.blockSignals(False)
        self._fit_width = False
        self._fit_height = False
        self._zoom = min(5.0, self._zoom * 1.2)
        self._render()

    def zoom_out(self) -> None:
        self._fit_width_cb.blockSignals(True)
        self._fit_height_cb.blockSignals(True)
        self._fit_width_cb.setChecked(False)
        self._fit_height_cb.setChecked(False)
        self._fit_width_cb.blockSignals(False)
        self._fit_height_cb.blockSignals(False)
        self._fit_width = False
        self._fit_height = False
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
                    self._fit_width_cb.blockSignals(True)
                    self._fit_height_cb.blockSignals(True)
                    self._fit_width_cb.setChecked(False)
                    self._fit_height_cb.setChecked(False)
                    self._fit_width_cb.blockSignals(False)
                    self._fit_height_cb.blockSignals(False)
                    self._fit_width = False
                    self._fit_height = False
                    self._zoom = max(0.1, min(10.0, self._zoom + delta * 0.15))
                    self._render()
                    return True
                else:
                    sb = self._scroll.verticalScrollBar()
                    at_bottom = sb.value() >= sb.maximum()
                    at_top = sb.value() <= 0
                    if event.angleDelta().y() < 0 and at_bottom:
                        self._next_page()
                    elif event.angleDelta().y() > 0 and at_top:
                        self._prev_page()
                    return False
        return super().eventFilter(obj, event)
