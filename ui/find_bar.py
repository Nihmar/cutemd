"""Find bar widget — inline search with highlights and match navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QToolButton,
    QWidget,
)


class FindBar(QWidget):
    """Inline find bar that attaches to a QPlainTextEdit."""

    closed = Signal()
    highlights_changed = Signal()

    def __init__(self, editor: QPlainTextEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._selections: list[QTextEdit.ExtraSelection] = []
        self.setVisible(False)
        self.setFixedHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText(self.tr("Find\u2026"))
        self._input.setMaximumWidth(200)
        self._input.setFixedHeight(24)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._find_next)

        self._count_label = QLabel()

        self._case_btn = QToolButton()
        self._case_btn.setText("Aa")
        self._case_btn.setCheckable(True)
        self._case_btn.setToolTip(self.tr("Match case"))
        self._case_btn.setFixedSize(28, 24)
        self._case_btn.toggled.connect(self._highlight_all)

        prev_btn = QToolButton()
        prev_btn.setText("\u25b2")
        prev_btn.setToolTip(self.tr("Previous match"))
        prev_btn.setFixedSize(28, 24)
        prev_btn.clicked.connect(self._find_prev)

        next_btn = QToolButton()
        next_btn.setText("\u25bc")
        next_btn.setToolTip(self.tr("Next match"))
        next_btn.setFixedSize(28, 24)
        next_btn.clicked.connect(self._find_next)

        close_btn = QToolButton()
        close_btn.setText("\u2715")
        close_btn.setToolTip(self.tr("Close find bar"))
        close_btn.setFixedSize(28, 24)
        close_btn.clicked.connect(self.close)

        layout.addWidget(self._input)
        layout.addWidget(self._count_label)
        layout.addStretch()
        layout.addWidget(self._case_btn)
        layout.addWidget(prev_btn)
        layout.addWidget(next_btn)
        layout.addWidget(close_btn)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def selections(self) -> list[QTextEdit.ExtraSelection]:
        return self._selections

    def open(self) -> None:
        self.setVisible(True)
        self._input.setFocus()
        self._input.selectAll()
        if self._editor.textCursor().hasSelection():
            self._input.setText(self._editor.textCursor().selectedText())
        self._selections = []

    def close(self) -> None:
        self.setVisible(False)
        self._clear_highlights()
        self._editor.setFocus()
        self.closed.emit()

    def update_highlights(self) -> None:
        self._highlight_all()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _flags(self) -> QTextDocument.FindFlag | QTextDocument.FindFlags:
        flags: QTextDocument.FindFlag = QTextDocument.FindFlag(0)
        if self._case_btn.isChecked():
            flags = QTextDocument.FindFlag.FindCaseSensitively  # type: ignore[assignment]
        return flags  # type: ignore[return-value]

    def _highlight_all(self) -> None:
        term = self._input.text()
        if not term:
            self._clear_highlights()
            return
        flags = self._flags()
        doc = self._editor.document()
        self._selections = []
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(term, cursor, flags)
            if cursor.isNull():
                break
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(100, 100, 100))
            sel = QTextEdit.ExtraSelection()
            sel.format = fmt
            sel.cursor = QTextCursor(cursor)
            self._selections.append(sel)
        self._apply_selections()
        self._update_count_label()

    def _update_count_label(self) -> None:
        count = len(self._selections)
        if count > 0:
            cursor = self._editor.textCursor()
            found = -1
            cp = cursor.position()
            anchor = cursor.anchor()
            for i, sel in enumerate(self._selections):
                if sel.cursor.selectionStart() <= cp and sel.cursor.selectionEnd() >= cp:
                    found = i
                    break
                if sel.cursor.selectionStart() == cp and sel.cursor.selectionEnd() == anchor:
                    found = i
                    break
            if found >= 0:
                self._count_label.setText(f"{found + 1}/{count}")
            else:
                self._count_label.setText(f"0/{count}")
        else:
            self._count_label.setText("0/0")

    def _clear_highlights(self) -> None:
        self._selections = []
        self._apply_selections()

    def _apply_selections(self) -> None:
        self.highlights_changed.emit()

    def _on_text_changed(self, _text: str) -> None:
        self._highlight_all()
        self._find_next()

    def _find_next(self) -> None:
        term = self._input.text()
        if not term:
            return
        flags = self._flags()
        found = self._editor.find(term, flags)
        if not found:
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._editor.setTextCursor(cursor)
            self._editor.find(term, flags)
        self._update_count_label()

    def _find_prev(self) -> None:
        term = self._input.text()
        if not term:
            return
        flags = self._flags() | QTextDocument.FindFlag.FindBackward
        found = self._editor.find(term, flags)
        if not found:
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._editor.setTextCursor(cursor)
            self._editor.find(term, flags)
        self._update_count_label()
