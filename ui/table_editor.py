"""Table editing helpers: popup editor, insert dialog, table detection.

Provides a QTableWidget-based popup for structured editing of
Markdown pipe tables, a dimensions dialog for inserting new tables,
and utility functions for detecting / navigating table cells in
plain-text source.
"""

from __future__ import annotations

import re
from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.logging import setup_logging

_LOG = setup_logging("cutemd.table_editor")


# ---------------------------------------------------------------------------
# Table detection / parsing
# ---------------------------------------------------------------------------

# Matches a full pipe-table row:  | col1 | col2 | ... |
_ROW_RE = re.compile(r"^\|(.+)\|\s*$")

# Separator row:  |---|---|  (at least one dash per column, optional colons)
_SEP_RE = re.compile(r"^\|(\s*:?-+:?\s*\|)+\s*$", re.IGNORECASE)


def _find_table_range(cursor: QTextCursor) -> tuple[int, int] | None:
    """Return ``(start_block, end_block)`` (inclusive) of the pipe table
    surrounding *cursor*, or ``None`` if not inside a table."""
    doc = cursor.document()
    bn = cursor.block().blockNumber()

    # Walk upward to find table start
    top = bn
    while top > 0:
        prev = doc.findBlockByNumber(top - 1).text()
        if _ROW_RE.match(prev) or _SEP_RE.match(prev):
            top -= 1
        else:
            break

    # Walk downward to find table end
    bottom = bn
    total = doc.blockCount()
    while bottom < total - 1:
        nxt = doc.findBlockByNumber(bottom + 1).text()
        if _ROW_RE.match(nxt):
            bottom += 1
        else:
            break

    # A valid table needs at least a separator row
    has_sep = False
    for n in range(top, bottom + 1):
        if _SEP_RE.match(doc.findBlockByNumber(n).text()):
            has_sep = True
            break
    if not has_sep:
        return None
    return (top, bottom)


def is_in_table(cursor: QTextCursor) -> bool:
    """Return True if *cursor* is inside a pipe table."""
    return _find_table_range(cursor) is not None


def parse_table(cursor: QTextCursor) -> tuple[list[list[str]], int, int] | None:
    """Parse the pipe table surrounding *cursor*.

    Returns ``(rows, sep_index, col_index)`` where *rows* is a list of
    cell-value rows (separator row excluded), *sep_index* is the row
    index of the separator line, and *col_index* is the 0‑based column
    the cursor is in.  Returns None if not inside a valid table.
    """
    rng = _find_table_range(cursor)
    if rng is None:
        return None
    top, bottom = rng
    doc = cursor.document()

    pos_in_block = cursor.positionInBlock()
    col = _column_at_pos(cursor.block().text(), pos_in_block)

    rows: list[list[str]] = []
    sep_idx = -1
    for n in range(top, bottom + 1):
        text = doc.findBlockByNumber(n).text()
        if _SEP_RE.match(text):
            sep_idx = n - top
            continue
        m = _ROW_RE.match(text)
        if m:
            cells = [c.strip() for c in m.group(1).split("|")]
            rows.append(cells)

    if sep_idx < 0 or not rows:
        return None
    return rows, sep_idx, col


def _column_at_pos(line: str, pos: int) -> int:
    """Return the 0‑based column index for position *pos* in a pipe-table row."""
    col = 0
    for i, ch in enumerate(line):
        if i >= pos:
            break
        if ch == "|":
            col += 1
    # Position is after the opening | so column is col - 1
    return max(0, col - 1)


def _cell_position(block_text: str, col: int) -> tuple[int, int]:
    """Return ``(start, end)`` positions of column *col* in *block_text*."""
    parts = block_text.split("|")
    # parts[0] is empty (before first |), parts[1] is first cell, etc.
    idx = col + 1
    if idx >= len(parts):
        return len(block_text), len(block_text)
    # Find start position (after the col-th |)
    pos = 0
    for i in range(idx):
        pos = block_text.index("|", pos) + 1
    start = pos
    end = start + len(parts[idx])
    return start, end


# ---------------------------------------------------------------------------
# Table popup editor
# ---------------------------------------------------------------------------


class TablePopupEditor(QDialog):
    """A QTableWidget-based dialog for structured editing of a Markdown pipe table.

    On accept, calls ``on_apply(rows: list[list[str]])`` with the edited
    data so the caller can serialise it back to Markdown.
    """

    def __init__(self, rows: list[list[str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit Table"))
        self.setMinimumSize(500, 300)
        self._rows = [list(r) for r in rows]
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Toolbar
        tb = QHBoxLayout()
        self._add_col_btn = QPushButton(self.tr("+ Column"))
        self._add_col_btn.clicked.connect(self._add_column)
        self._del_col_btn = QPushButton(self.tr("− Column"))
        self._del_col_btn.clicked.connect(self._del_column)
        self._add_row_btn = QPushButton(self.tr("+ Row"))
        self._add_row_btn.clicked.connect(self._add_row)
        self._del_row_btn = QPushButton(self.tr("− Row"))
        self._del_row_btn.clicked.connect(self._del_row)
        tb.addWidget(self._add_col_btn)
        tb.addWidget(self._del_col_btn)
        tb.addWidget(self._add_row_btn)
        tb.addWidget(self._del_row_btn)
        tb.addStretch()
        layout.addLayout(tb)

        # Table widget
        self._table = QTableWidget(self)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _populate(self) -> None:
        if not self._rows:
            self._rows = [[""]]
        ncols = max(len(r) for r in self._rows)
        # Normalise all rows to same column count
        for r in self._rows:
            while len(r) < ncols:
                r.append("")
        self._table.setColumnCount(ncols)
        self._table.setRowCount(len(self._rows))
        for ri, row in enumerate(self._rows):
            for ci, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(ri, ci, item)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self._del_col_btn.setEnabled(self._table.columnCount() > 1)
        self._del_row_btn.setEnabled(self._table.rowCount() > 1)

    def _add_column(self) -> None:
        self._table.setColumnCount(self._table.columnCount() + 1)
        for ri in range(self._table.rowCount()):
            if self._table.item(ri, self._table.columnCount() - 1) is None:
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(ri, self._table.columnCount() - 1, item)
        self._update_buttons()

    def _del_column(self) -> None:
        if self._table.columnCount() > 1:
            self._table.setColumnCount(self._table.columnCount() - 1)
        self._update_buttons()

    def _add_row(self) -> None:
        ri = self._table.rowCount()
        self._table.setRowCount(ri + 1)
        for ci in range(self._table.columnCount()):
            item = QTableWidgetItem("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(ri, ci, item)
        self._update_buttons()

    def _del_row(self) -> None:
        if self._table.rowCount() > 1:
            self._table.setRowCount(self._table.rowCount() - 1)
        self._update_buttons()

    def _on_accept(self) -> None:
        rows: list[list[str]] = []
        for ri in range(self._table.rowCount()):
            row: list[str] = []
            for ci in range(self._table.columnCount()):
                item = self._table.item(ri, ci)
                row.append(item.text() if item else "")
            rows.append(row)
        self._rows = rows
        self.accept()

    def result_rows(self) -> list[list[str]]:
        return [list(r) for r in self._rows]


# ---------------------------------------------------------------------------
# Markdown serialization
# ---------------------------------------------------------------------------


def rows_to_markdown(rows: Sequence[Sequence[str]], col_align: Sequence[str] | None = None) -> str:
    """Convert *rows* to a Markdown pipe table string."""
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    # Normalise rows
    normalised: list[list[str]] = []
    for r in rows:
        nr = list(r)
        while len(nr) < ncols:
            nr.append("")
        normalised.append(nr)
    # Column widths for alignment
    widths = [0] * ncols
    for row in normalised:
        for ci, cell in enumerate(row):
            widths[ci] = max(widths[ci], len(cell))
    # Build lines
    lines: list[str] = []
    for ri, row in enumerate(normalised):
        line = "| " + " | ".join(c.ljust(widths[ci]) for ci, c in enumerate(row)) + " |"
        lines.append(line)
        if ri == 0:
            # Separator row
            if col_align and len(col_align) == ncols:
                seps = []
                for ci, a in enumerate(col_align):
                    w = widths[ci]
                    if a == "center" or a == "c":
                        seps.append(":" + "-" * max(1, w) + ":")
                    elif a == "right" or a == "r":
                        seps.append("-" * max(1, w) + ":")
                    elif a == "left" or a == "l":
                        seps.append(":" + "-" * max(1, w))
                    else:
                        seps.append("-" * max(1, w + 2))
            else:
                seps = ["-" * max(3, widths[ci]) for ci in range(ncols)]
            lines.append("|" + "|".join(seps) + "|")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Insert table dialog
# ---------------------------------------------------------------------------


class InsertTableDialog(QDialog):
    """Simple dialog asking for rows × columns to insert a new pipe table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Insert Table"))
        layout = QVBoxLayout(self)

        grid = QHBoxLayout()
        grid.addWidget(QLabel(self.tr("Columns:")))
        self._col_spin = QSpinBox(self)
        self._col_spin.setRange(1, 20)
        self._col_spin.setValue(3)
        grid.addWidget(self._col_spin)
        grid.addWidget(QLabel(self.tr("Rows:")))
        self._row_spin = QSpinBox(self)
        self._row_spin.setRange(1, 50)
        self._row_spin.setValue(3)
        grid.addWidget(self._row_spin)
        layout.addLayout(grid)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def dimensions(self) -> tuple[int, int]:
        return self._row_spin.value(), self._col_spin.value()


# ---------------------------------------------------------------------------
# Table navigation (Tab key)
# ---------------------------------------------------------------------------


def move_to_next_cell(editor: QPlainTextEdit) -> bool:
    """If the cursor is inside a table, move it to the next cell.

    At the last cell of the last row, a new row is appended.
    Returns True if the cursor was moved / action taken.
    """
    cursor = editor.textCursor()
    rng = _find_table_range(cursor)
    if rng is None:
        return False
    top, bottom = rng
    doc = cursor.document()
    bn = cursor.block().blockNumber()
    pos = cursor.positionInBlock()

    row_texts = []
    sep_line = -1
    for n in range(top, bottom + 1):
        t = doc.findBlockByNumber(n).text()
        if _SEP_RE.match(t):
            sep_line = n
            continue
        if _ROW_RE.match(t):
            row_texts.append((n, t))

    if not row_texts or sep_line < 0:
        return False

    # Current logical row index (0‑based, skipping separator)
    cur_logical = -1
    for i, (rn, _) in enumerate(row_texts):
        if rn == bn:
            cur_logical = i
            break
    if cur_logical < 0:
        return False

    line = cursor.block().text()
    col = _column_at_pos(line, pos)
    ncols = max(len(_ROW_RE.match(t).group(1).split("|"))  # type: ignore[union-attr]
                for _, t in row_texts)

    if col + 1 < ncols:
        # Move to next column in current row
        _, start, end = _cell_bounds(line, col + 1)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, start + 1)
        editor.setTextCursor(cursor)
        return True
    elif cur_logical + 1 < len(row_texts):
        # Move to first column of next row
        next_bn, next_text = row_texts[cur_logical + 1]
        _, start, _ = _cell_bounds(next_text, 0)
        block = doc.findBlockByNumber(next_bn)
        cursor.setPosition(block.position() + start + 1)
        editor.setTextCursor(cursor)
        return True
    else:
        # Last cell — append a new row
        return _append_table_row(editor, top, bottom, ncols)


def _cell_bounds(line: str, col: int) -> tuple[int, int, int]:
    """Return ``(length, start, end)`` of column *col* in *line*.

    *length* is the length of the full line text (including trailing
    whitespace), *start* and *end* are positions within the cell content.
    """
    parts = line.split("|")
    idx = col + 1
    if idx >= len(parts):
        return len(line), len(line), len(line)
    pos = 0
    for i in range(idx):
        pos = line.index("|", pos) + 1
    start = pos
    end = start + len(parts[idx])
    return len(line), start, end


def _append_table_row(editor: QPlainTextEdit, top: int, bottom: int, ncols: int) -> bool:
    """Append an empty row to the table spanning *top*…*bottom*."""
    cursor = editor.textCursor()
    doc = cursor.document()
    last_block = doc.findBlockByNumber(bottom)
    cursor.setPosition(last_block.position() + last_block.length() - 1)

    cells = " | ".join(" " for _ in range(ncols))
    cursor.insertText("\n| " + cells + " |")

    # Move cursor to first cell of the new row
    editor.setTextCursor(cursor)
    return True


def move_to_prev_cell(editor: QPlainTextEdit) -> bool:
    """Shift+Tab inside a table: move to previous cell."""
    cursor = editor.textCursor()
    rng = _find_table_range(cursor)
    if rng is None:
        return False
    top, bottom = rng
    doc = cursor.document()
    bn = cursor.block().blockNumber()
    pos = cursor.positionInBlock()
    line = cursor.block().text()

    col = _column_at_pos(line, pos)

    row_texts = []
    for n in range(top, bottom + 1):
        t = doc.findBlockByNumber(n).text()
        if _SEP_RE.match(t):
            continue
        if _ROW_RE.match(t):
            row_texts.append((n, t))

    cur_logical = -1
    for i, (rn, _) in enumerate(row_texts):
        if rn == bn:
            cur_logical = i
            break
    if cur_logical < 0:
        return False

    if col > 0:
        # Previous column in same row
        _, start, _ = _cell_bounds(line, col - 1)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, start + 1)
        editor.setTextCursor(cursor)
        return True
    elif cur_logical > 0:
        # Last column of previous row
        prev_bn, prev_text = row_texts[cur_logical - 1]
        ncols = max(len(_ROW_RE.match(t).group(1).split("|"))  # type: ignore[union-attr]
                    for _, t in row_texts)
        _, start, _ = _cell_bounds(prev_text, ncols - 1)
        block = doc.findBlockByNumber(prev_bn)
        cursor.setPosition(block.position() + start + 1)
        editor.setTextCursor(cursor)
        return True
    return False


# ---------------------------------------------------------------------------
# Context menu helpers
# ---------------------------------------------------------------------------


def add_table_context_actions(
    menu, editor: QPlainTextEdit, on_edit_table, on_add_row, on_add_col
) -> None:
    """Append table-specific actions to *menu* if the cursor is in a table."""
    cursor = editor.textCursor()
    if not is_in_table(cursor):
        return
    menu.addSeparator()
    menu.addAction(editor.tr("Edit Table…")).triggered.connect(on_edit_table)
    menu.addAction(editor.tr("Add Row")).triggered.connect(on_add_row)
    menu.addAction(editor.tr("Add Column")).triggered.connect(on_add_col)
