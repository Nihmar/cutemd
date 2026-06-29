"""Conflict resolution UI for WebDAV sync.

Provides dialogs for resolving sync conflicts:
- Binary files: simple metadata comparison, pick local or remote
- Markdown files: side-by-side diff view using difflib, accept local,
  remote, or manually edit the merged result
- Conflict markers (git-style) as a fallback
"""

from __future__ import annotations

import difflib
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.logging import setup_logging

_LOG = setup_logging("cutemd.conflict_resolver")

# Binary file extensions
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".pdf", ".ico", ".zip", ".gz", ".tar",
}


# ---------------------------------------------------------------------------
# Diff highlighter (green for added, red for removed)
# ---------------------------------------------------------------------------


class _DiffHighlighter(QSyntaxHighlighter):
    """Highlight diff output: green for additions, red for deletions."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._add_fmt = QTextCharFormat()
        self._add_fmt.setBackground(QColor("#d4edda"))  # light green
        self._add_fmt.setForeground(QColor("#155724"))
        self._del_fmt = QTextCharFormat()
        self._del_fmt.setBackground(QColor("#f8d7da"))  # light red
        self._del_fmt.setForeground(QColor("#721c24"))
        self._hdr_fmt = QTextCharFormat()
        self._hdr_fmt.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str) -> None:
        if text.startswith("@@"):
            self.setFormat(0, len(text), self._hdr_fmt)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self._add_fmt)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._del_fmt)


# ---------------------------------------------------------------------------
# Conflict result
# ---------------------------------------------------------------------------


class ConflictResolution:
    """Holds the user's resolution for a single conflict."""

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.action: str = "skip"        # keep_local | take_remote | merged | skip
        self.merged_content: str | None = None  # only for markdown merges


# ---------------------------------------------------------------------------
# Binary conflict dialog
# ---------------------------------------------------------------------------


class BinaryConflictDialog(QDialog):
    """Simple dialog: show metadata for both versions, pick one."""

    def __init__(
        self,
        rel_path: str,
        local_size: int,
        local_mtime: str,
        remote_size: int,
        remote_mtime: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sync Conflict — {}").format(rel_path))
        self.setMinimumWidth(480)
        self._action = "skip"

        layout = QVBoxLayout(self)

        label = QLabel(
            self.tr("Both local and remote versions have changed.\n"
                    "Choose which version to keep:")
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        # Local info
        local_frame = QFrame(self)
        local_frame.setFrameStyle(QFrame.Shape.Box)
        local_layout = QVBoxLayout(local_frame)
        local_layout.addWidget(QLabel(f"<b>{self.tr('Local')}</b>"))
        local_layout.addWidget(QLabel(self.tr("Size: {} bytes").format(local_size)))
        local_layout.addWidget(QLabel(self.tr("Modified: {}").format(local_mtime)))
        layout.addWidget(local_frame)

        # Remote info
        remote_frame = QFrame(self)
        remote_frame.setFrameStyle(QFrame.Shape.Box)
        remote_layout = QVBoxLayout(remote_frame)
        remote_layout.addWidget(QLabel(f"<b>{self.tr('Remote')}</b>"))
        remote_layout.addWidget(QLabel(self.tr("Size: {} bytes").format(remote_size)))
        remote_layout.addWidget(QLabel(self.tr("Modified: {}").format(remote_mtime)))
        layout.addWidget(remote_frame)

        # Buttons
        btns = QHBoxLayout()
        keep_local = QPushButton(self.tr("Keep Local"))
        keep_local.clicked.connect(lambda: self._choose("keep_local"))
        keep_remote = QPushButton(self.tr("Take Remote"))
        keep_remote.clicked.connect(lambda: self._choose("take_remote"))
        skip_btn = QPushButton(self.tr("Skip"))
        skip_btn.clicked.connect(lambda: self._choose("skip"))
        btns.addWidget(keep_local)
        btns.addWidget(keep_remote)
        btns.addWidget(skip_btn)
        layout.addLayout(btns)

    def _choose(self, action: str) -> None:
        self._action = action
        self.accept()

    @property
    def action(self) -> str:
        return self._action


# ---------------------------------------------------------------------------
# Markdown diff / merge dialog
# ---------------------------------------------------------------------------


class MarkdownConflictDialog(QDialog):
    """Side-by-side diff view for Markdown conflicts."""

    def __init__(
        self,
        rel_path: str,
        local_text: str,
        remote_text: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sync Conflict — {}").format(rel_path))
        self.resize(1000, 600)
        self._action = "skip"
        self._merged_text: str | None = None
        self._rel_path = rel_path

        layout = QVBoxLayout(self)

        label = QLabel(
            self.tr("Both versions have changed. Choose how to resolve:")
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        # Splitter with local, diff, remote panes
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Local pane
        local_widget = QWidget()
        local_layout = QVBoxLayout(local_widget)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.addWidget(QLabel(f"<b>{self.tr('Local')}</b>"))
        self._local_edit = QPlainTextEdit()
        self._local_edit.setReadOnly(True)
        self._local_edit.setPlainText(local_text)
        self._local_edit.setTabStopDistance(40)
        font = self._local_edit.font()
        font.setFamily("monospace")
        font.setPointSize(10)
        self._local_edit.setFont(font)
        local_layout.addWidget(self._local_edit)
        splitter.addWidget(local_widget)

        # Diff pane (unified diff)
        diff_widget = QWidget()
        diff_layout = QVBoxLayout(diff_widget)
        diff_layout.setContentsMargins(0, 0, 0, 0)
        diff_layout.addWidget(QLabel(f"<b>{self.tr('Diff')}</b>"))
        self._diff_edit = QPlainTextEdit()
        self._diff_edit.setReadOnly(True)
        diff_text = "\n".join(
            difflib.unified_diff(
                local_text.splitlines(),
                remote_text.splitlines(),
                fromfile=self.tr("local"),
                tofile=self.tr("remote"),
                lineterm="",
            )
        )
        if not diff_text:
            diff_text = self.tr("(no differences)")
        self._diff_edit.setPlainText(diff_text)
        self._diff_edit.setFont(font)
        self._highlighter = _DiffHighlighter(self._diff_edit.document())
        diff_layout.addWidget(self._diff_edit)
        splitter.addWidget(diff_widget)

        # Remote pane
        remote_widget = QWidget()
        remote_layout = QVBoxLayout(remote_widget)
        remote_layout.setContentsMargins(0, 0, 0, 0)
        remote_layout.addWidget(QLabel(f"<b>{self.tr('Remote')}</b>"))
        self._remote_edit = QPlainTextEdit()
        self._remote_edit.setReadOnly(True)
        self._remote_edit.setPlainText(remote_text)
        self._remote_edit.setFont(font)
        remote_layout.addWidget(self._remote_edit)
        splitter.addWidget(remote_widget)

        splitter.setSizes([330, 330, 330])
        layout.addWidget(splitter)

        # Conflict marker fallback
        cb_layout = QHBoxLayout()
        self._marker_cb = QCheckBox(
            self.tr("Use conflict markers (git-style) as fallback output")
        )
        cb_layout.addWidget(self._marker_cb)
        cb_layout.addStretch()
        layout.addLayout(cb_layout)

        # Buttons
        btns = QHBoxLayout()
        keep_local = QPushButton(self.tr("Keep Local"))
        keep_local.clicked.connect(lambda: self._choose("keep_local"))
        keep_remote = QPushButton(self.tr("Take Remote"))
        keep_remote.clicked.connect(lambda: self._choose("take_remote"))
        merge_btn = QPushButton(self.tr("Merge with Markers"))
        merge_btn.clicked.connect(self._merge_with_markers)
        skip_btn = QPushButton(self.tr("Skip"))
        skip_btn.clicked.connect(lambda: self._choose("skip"))
        btns.addWidget(keep_local)
        btns.addWidget(keep_remote)
        btns.addWidget(merge_btn)
        btns.addWidget(skip_btn)
        layout.addLayout(btns)

    def _choose(self, action: str) -> None:
        self._action = action
        self.accept()

    def _merge_with_markers(self) -> None:
        local = self._local_edit.toPlainText()
        remote = self._remote_edit.toPlainText()
        self._merged_text = (
            f"<<<<<<< LOCAL ({self._rel_path})\n"
            f"{local}\n"
            f"=======\n"
            f"{remote}\n"
            f">>>>>>> REMOTE\n"
        )
        self._action = "merged"
        self.accept()

    @property
    def action(self) -> str:
        return self._action

    @property
    def merged_content(self) -> str | None:
        return self._merged_text


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def is_binary_file(path_str: str) -> bool:
    """Return True if the file path looks like a binary type."""
    return Path(path_str).suffix.lower() in _BINARY_EXTS
