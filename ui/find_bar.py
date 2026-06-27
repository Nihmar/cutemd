"""Find-and-replace bar widget — inline search with highlights, match
navigation, and replace operations (single + replace all)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class FindBar(QWidget):
    """Inline find-and-replace bar for a QPlainTextEdit."""

    closed = Signal()
    highlights_changed = Signal()

    def __init__(self, editor: QPlainTextEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._selections: list[QTextEdit.ExtraSelection] = []
        self.setVisible(False)
        self.setObjectName("findBar")
        self.setMinimumHeight(80)
        self.setMaximumHeight(86)

        # ── Row 1: find ───────────────────────────────────────────────
        self._input = QLineEdit()
        self._input.setPlaceholderText(self.tr("Find\u2026"))
        self._input.setMaximumWidth(200)
        self._input.setMinimumHeight(26)
        self._input.textChanged.connect(self._on_find_text_changed)
        self._input.returnPressed.connect(self._find_next)

        self._count_label = QLabel()
        self._count_label.setFixedHeight(24)

        self._case_btn = QPushButton()
        self._case_btn.setText("Aa")
        self._case_btn.setCheckable(True)
        self._case_btn.setToolTip(self.tr("Match case"))
        self._case_btn.setFixedSize(28, 24)
        self._case_btn.toggled.connect(self._highlight_all)

        prev_btn = QPushButton()
        prev_btn.setText("\u25b2")
        prev_btn.setToolTip(self.tr("Previous match"))
        prev_btn.setFixedSize(28, 24)
        prev_btn.clicked.connect(self._find_prev)

        next_btn = QPushButton()
        next_btn.setText("\u25bc")
        next_btn.setToolTip(self.tr("Next match"))
        next_btn.setFixedSize(28, 24)
        next_btn.clicked.connect(self._find_next)

        close_btn = QPushButton()
        close_btn.setText("\u2715")
        close_btn.setToolTip(self.tr("Close find bar"))
        close_btn.setFixedSize(28, 24)
        close_btn.clicked.connect(self.close)

        find_row_widget = QWidget()
        find_row = QHBoxLayout(find_row_widget)
        find_row.setContentsMargins(0, 0, 0, 0)
        find_row.setSpacing(6)
        find_row.addWidget(self._input, 0, Qt.AlignmentFlag.AlignVCenter)
        find_row.addWidget(self._count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        find_row.addStretch()
        find_row.addWidget(self._case_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        find_row.addWidget(prev_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        find_row.addWidget(next_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        find_row.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Row 2: replace ────────────────────────────────────────────
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText(self.tr("Replace\u2026"))
        self._replace_input.setMaximumWidth(200)
        self._replace_input.setMinimumHeight(26)
        self._replace_input.returnPressed.connect(self._replace_one)

        replace_btn = QPushButton()
        replace_btn.setText(self.tr("Replace"))
        replace_btn.setToolTip(self.tr("Replace current match"))
        replace_btn.setFixedHeight(24)
        replace_btn.clicked.connect(self._replace_one)

        replace_all_btn = QPushButton()
        replace_all_btn.setText(self.tr("Replace All"))
        replace_all_btn.setToolTip(self.tr("Replace all matches"))
        replace_all_btn.setFixedHeight(24)
        replace_all_btn.clicked.connect(self._replace_all)

        replace_row_widget = QWidget()
        replace_row = QHBoxLayout(replace_row_widget)
        replace_row.setContentsMargins(0, 0, 0, 0)
        replace_row.setSpacing(6)
        replace_row.addWidget(self._replace_input, 0, Qt.AlignmentFlag.AlignVCenter)
        replace_row.addWidget(replace_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        replace_row.addWidget(replace_all_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        replace_row.addStretch()

        # ── Outer layout ──────────────────────────────────────────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 8)
        outer.setSpacing(4)
        outer.addWidget(find_row_widget)
        outer.addWidget(replace_row_widget)

        # ── Tab navigation between find ↔ replace inputs ────────────
        self._input.installEventFilter(self)
        self._replace_input.installEventFilter(self)

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

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event  # type: ignore[assignment]
            if key_event.key() == Qt.Key.Key_Tab:
                if obj is self._input:
                    self._replace_input.setFocus()
                    self._replace_input.selectAll()
                    return True
                elif obj is self._replace_input:
                    self._input.setFocus()
                    self._input.selectAll()
                    return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------
    def _flags(self) -> QTextDocument.FindFlag | QTextDocument.FindFlags:
        flags: QTextDocument.FindFlag = QTextDocument.FindFlag(0)
        if self._case_btn.isChecked():
            flags = QTextDocument.FindFlag.FindCaseSensitively  # type: ignore[assignment]
        return flags  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Highlight all matches
    # ------------------------------------------------------------------
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
        if count == 0:
            self._count_label.setText("0/0")
            return
        cursor = self._editor.textCursor()
        cp = cursor.position()
        anchor = cursor.anchor()
        found = -1
        for i, sel in enumerate(self._selections):
            if sel.cursor.selectionStart() <= cp <= sel.cursor.selectionEnd():
                found = i
                break
            if (
                sel.cursor.selectionStart() == cp
                and sel.cursor.selectionEnd() == anchor
            ):
                found = i
                break
        if found >= 0:
            self._count_label.setText(f"{found + 1}/{count}")
        else:
            self._count_label.setText(f"0/{count}")

    def _clear_highlights(self) -> None:
        self._selections = []
        self._apply_selections()

    def _apply_selections(self) -> None:
        self.highlights_changed.emit()

    # ------------------------------------------------------------------
    # Find navigation
    # ------------------------------------------------------------------
    def _on_find_text_changed(self, _text: str) -> None:
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

    # ------------------------------------------------------------------
    # Replace
    # ------------------------------------------------------------------
    def _replace_one(self) -> None:
        """Replace the current match and advance to the next."""
        term = self._input.text()
        if not term:
            return
        cursor = self._editor.textCursor()
        # Only replace if the cursor is currently on a match
        flags = self._flags()
        # Check if selected text matches the find term
        if cursor.hasSelection():
            sel_text = cursor.selectedText()
            if self._case_btn.isChecked():
                matches = sel_text == term
            else:
                matches = sel_text.lower() == term.lower()
        else:
            # Try to select the term at the current cursor position
            old_pos = cursor.position()
            found = self._editor.find(term, flags)
            if found:
                matches = True
                # cursor was moved by find(); the selected text is the match
            else:
                # Wrap around
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                self._editor.setTextCursor(cursor)
                found = self._editor.find(term, flags)
                matches = found
            if not found:
                return

        if matches:
            replacement = self._replace_input.text()
            cursor = self._editor.textCursor()
            cursor.insertText(replacement)
        # Advance to next match
        self._highlight_all()
        self._find_next()

    def _replace_all(self) -> None:
        """Replace every occurrence of the find term in the document."""
        term = self._input.text()
        if not term:
            return
        replacement = self._replace_input.text()
        flags = self._flags()

        doc = self._editor.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()

        count = 0
        while True:
            cursor = doc.find(term, cursor, flags)
            if cursor.isNull():
                break
            cursor.insertText(replacement)
            count += 1

        cursor.endEditBlock()

        # Re-highlight (should show 0 matches if term != replacement)
        self._highlight_all()
