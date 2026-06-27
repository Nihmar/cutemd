"""Toggle switch widget styled after KDE Plasma / Breeze.

The track is a narrow pill ("rail") and the thumb circle is taller,
overflowing above and below — exactly like the Breeze toggle.

OFF  — outlined rail, bordered thumb on left.
ON   — filled rail (highlight colour), white thumb on right.

Supports disabled state, smooth animation, and is QCheckBox-compatible
(isChecked/setChecked).
"""

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

_ANIM_DURATION = 120  # ms


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
        self._anim_progress = 1.0 if checked else 0.0  # fully settled
        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # --- public API (QCheckBox-compatible) ---

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        if self._checked != checked:
            self._checked = checked
            self._start_animation()
            self.toggled.emit(self._checked)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        if enabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        self.update()

    # --- animation ---

    def _start_animation(self) -> None:
        if hasattr(self, "_anim"):
            self._anim.stop()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(_ANIM_DURATION)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(self._anim_progress)
        self._anim.setEndValue(1.0 if self._checked else 0.0)
        self._anim.valueChanged.connect(self._on_anim_step)
        self._anim.start()

    def _on_anim_step(self, value: float) -> None:
        self._anim_progress = value
        self.update()

    # --- events ---

    def mousePressEvent(self, event) -> None:
        if self.isEnabled():
            self._checked = not self._checked
            self._start_animation()
            self.toggled.emit(self._checked)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pal = self.palette()
        disabled = not self.isEnabled()
        progress = getattr(self, "_anim_progress", 1.0 if self._checked else 0.0)

        # Track geometry (narrow rail, vertically centred)
        track_y = (self._H - self._TRACK_H) / 2.0
        track_rect = QRectF(0, track_y, self._W, self._TRACK_H)
        track_r = self._TRACK_H / 2.0

        # Thumb geometry — interpolate between off and on positions
        thumb_y = (self._H - self._THUMB) / 2.0
        thumb_off_x = self._MARGIN
        thumb_on_x = self._W - self._THUMB - self._MARGIN
        thumb_x = thumb_off_x + (thumb_on_x - thumb_off_x) * progress

        # ON colour lerp: track fills from outline to highlight
        highlight = pal.highlight().color()
        mid = pal.mid().color()
        rail_fill = QColor(
            int(mid.red() + (highlight.red() - mid.red()) * progress),
            int(mid.green() + (highlight.green() - mid.green()) * progress),
            int(mid.blue() + (highlight.blue() - mid.blue()) * progress),
        )

        if disabled:
            rail_fill.setAlpha(80)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rail_fill)
            p.drawRoundedRect(track_rect, track_r, track_r)
        elif progress > 0.01:
            if progress < 0.99:
                # Transitioning — draw filled portion + outline border
                p.setPen(QPen(mid, self._BORDER))
                p.setBrush(Qt.BrushStyle.NoBrush)
                inset = self._BORDER / 2.0
                p.drawRoundedRect(
                    track_rect.adjusted(inset, inset, -inset, -inset),
                    track_r, track_r,
                )
                # Filled portion behind the thumb
                fill_w = thumb_x + self._THUMB / 2
                if fill_w > 0:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(highlight)
                    clip = QRectF(0, track_y, fill_w, self._TRACK_H)
                    p.drawRoundedRect(clip, track_r, track_r)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(highlight)
                p.drawRoundedRect(track_rect, track_r, track_r)
        else:
            border = mid
            if disabled:
                border.setAlpha(60)
            pen = QPen(border, self._BORDER)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            inset = self._BORDER / 2.0
            p.drawRoundedRect(
                track_rect.adjusted(inset, inset, -inset, -inset),
                track_r, track_r,
            )

        # Thumb
        thumb_color = QColor(255, 255, 255) if progress > 0.5 else pal.window().color()
        thumb_border = highlight if progress > 0.5 else mid
        if disabled:
            thumb_color.setAlpha(100 if progress > 0.5 else 80)
            thumb_border.setAlpha(60)

        p.setPen(QPen(thumb_border, self._BORDER))
        p.setBrush(thumb_color)
        p.drawEllipse(QRectF(thumb_x, thumb_y, self._THUMB, self._THUMB))

        p.end()
