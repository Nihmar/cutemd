"""Toggle switch widget styled after KDE Plasma / Breeze.

The track is a narrow pill ("rail") and the thumb circle is taller,
overflowing above and below — exactly like the Breeze toggle.

OFF  — outlined rail, bordered thumb on left.
ON   — filled rail (highlight colour), white thumb on right.

Supports disabled state and is QCheckBox-compatible (isChecked/setChecked).
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ToggleSwitch(QWidget):
    """Toggle switch styled after KDE Plasma / Breeze."""

    toggled = Signal(bool)

    _W = 44   # total widget width
    _H = 22   # total widget height  (fits the thumb)
    _TRACK_H = 12  # narrow rail height
    _THUMB = 20    # thumb diameter  (> _TRACK_H → overflows)
    _BORDER = 1.5
    _MARGIN = 1    # gap between thumb edge and widget edge

    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # --- public API (QCheckBox-compatible) ---

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        if self._checked != checked:
            self._checked = checked
            self.update()
            self.toggled.emit(self._checked)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        if enabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        self.update()

    # --- events ---

    def mousePressEvent(self, event) -> None:
        if self.isEnabled():
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pal = self.palette()
        disabled = not self.isEnabled()

        # Track geometry (narrow rail, vertically centred)
        track_y = (self._H - self._TRACK_H) / 2.0
        track_rect = QRectF(0, track_y, self._W, self._TRACK_H)
        track_r = self._TRACK_H / 2.0

        # Thumb geometry (bigger circle, vertically centred)
        thumb_y = (self._H - self._THUMB) / 2.0
        thumb_off_x = self._MARGIN
        thumb_on_x = self._W - self._THUMB - self._MARGIN

        if self._checked:
            # ON — filled rail, white thumb on the right
            fill = pal.highlight().color()
            if disabled:
                fill.setAlpha(80)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(track_rect, track_r, track_r)

            thumb_c = QColor(255, 255, 255)
            if disabled:
                thumb_c.setAlpha(100)
            p.setBrush(thumb_c)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(thumb_on_x, thumb_y, self._THUMB, self._THUMB))
        else:
            # OFF — outlined rail, bordered thumb on the left
            border = pal.mid().color()
            if disabled:
                border.setAlpha(60)
            pen = QPen(border, self._BORDER)

            # Rail outline
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            inset = self._BORDER / 2.0
            p.drawRoundedRect(
                track_rect.adjusted(inset, inset, -inset, -inset),
                track_r,
                track_r,
            )

            # Thumb
            bg = pal.window().color()
            if disabled:
                bg.setAlpha(100)
            p.setBrush(bg)
            p.setPen(pen)
            p.drawEllipse(QRectF(thumb_off_x, thumb_y, self._THUMB, self._THUMB))

        p.end()
