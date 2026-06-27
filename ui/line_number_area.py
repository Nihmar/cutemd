"""Line number area widget — painted alongside a QPlainTextEdit.

Extracted from EditorTab to keep the tab class focused.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LineNumberArea(QWidget):
    """Widget that paints line numbers alongside the editor.

    Mode values:
        0 — hidden
        1 — every line
        2 — multiples of 5 (plus line 1 and the last line)
    """

    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor)
        self._editor = editor
        self._mode = 1

    def set_mode(self, mode: int) -> None:
        self._mode = mode
        self.update()

    def sizeHint(self) -> QSize:
        if self._mode == 0:
            return QSize(0, 0)
        return QSize(self._line_number_area_width(), 0)

    def _line_number_area_width(self) -> int:
        digits = len(str(max(1, self._editor.blockCount())))
        space = 10 + self._editor.fontMetrics().horizontalAdvance("9") * digits
        return space

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)
        if self._mode == 0:
            return
        painter = QPainter(self)
        painter.fillRect(
            event.rect(),
            QColor(
                self._editor.palette().color(self._editor.palette().ColorRole.Window)
            ),
        )

        block = self._editor.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(
            self._editor.blockBoundingGeometry(block)
            .translated(self._editor.contentOffset())
            .top()
        )
        bottom = top + int(self._editor.blockBoundingRect(block).height())

        fg = self._editor.palette().color(self._editor.palette().ColorRole.Mid)
        painter.setPen(fg)
        painter.setFont(self._editor.font())
        total_blocks = self._editor.blockCount()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = block_num + 1
                if self._mode == 1 or self._should_draw_line(line, total_blocks):
                    number = str(line)
                    painter.drawText(
                        0,
                        top,
                        self.width() - 4,
                        self._editor.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        number,
                    )
                elif self._mode == 2:
                    painter.drawText(
                        0,
                        top,
                        self.width() - 4,
                        self._editor.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        "·",
                    )
            block = block.next()
            top = bottom
            bottom = (
                top + int(self._editor.blockBoundingRect(block).height())
                if block.isValid()
                else top
            )
            block_num += 1

    @staticmethod
    def _should_draw_line(line: int, total: int) -> bool:
        return line == 1 or line == total or line % 5 == 0
