"""Zoomable/panning image viewer widget."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QLabel, QScrollArea, QWidget


class ImageViewer(QScrollArea):
    """Scrollable image viewer with Ctrl+scroll zoom and middle-click pan."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidgetResizable(True)
        self.setWidget(self._label)

        self._original: QPixmap | None = None
        self._zoom = 1.0
        self._pan_active = False

    def load(self, path: Path) -> bool:
        """Load an image from *path*."""
        self._original = QPixmap(str(path))
        self._zoom = 1.0
        if self._original.isNull():
            self._label.setText(self.tr("Cannot display this image format."))
            return False
        self._rescale()
        return True

    def _rescale(self) -> None:
        if self._original is None or self._original.isNull():
            return
        size = self.viewport().size()
        scaled = self._original.scaled(
            size * self._zoom,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def eventFilter(self, obj: object, event) -> bool:
        if obj is self.viewport():
            if event.type() == event.Type.Resize:
                self._rescale()
                return False
            if event.type() == event.Type.Wheel:
                we: QWheelEvent = event
                if we.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    delta = we.angleDelta().y() / 120.0
                    self._zoom = max(0.1, min(10.0, self._zoom + delta * 0.15))
                    self._rescale()
                    return True
            if event.type() == event.Type.MouseButtonPress:
                me: QMouseEvent = event
                if me.button() == Qt.MouseButton.MiddleButton:
                    self._pan_active = True
                    self._pan_last = me.position().toPoint()
                    self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True
            if event.type() == event.Type.MouseMove:
                if self._pan_active:
                    me: QMouseEvent = event
                    pt = me.position().toPoint()
                    delta = self._pan_last - pt
                    self._pan_last = pt
                    h = self.horizontalScrollBar()
                    v = self.verticalScrollBar()
                    if h:
                        h.setValue(h.value() + delta.x())
                    if v:
                        v.setValue(v.value() + delta.y())
                    return True
            if event.type() == event.Type.MouseButtonRelease:
                me: QMouseEvent = event
                if me.button() == Qt.MouseButton.MiddleButton:
                    self._pan_active = False
                    self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                    return True
        return super().eventFilter(obj, event)
