"""Update notification and download dialogs."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core.updater import UpdateInfo, check_for_update, download_release


class _CheckUpdateThread(QThread):
    """Calls the GitHub API in a background thread."""
    result = Signal(object)  # UpdateInfo | None

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self._version = current_version

    def run(self):
        info = check_for_update(self._version)
        self.result.emit(info)


class _DownloadThread(QThread):
    """Downloads the release asset in a background thread."""

    progress = Signal(int, int)  # (downloaded, total)
    finished = Signal(object)  # Path | None

    def __init__(self, update_info: UpdateInfo, parent=None):
        super().__init__(parent)
        self._info = update_info

    def run(self):
        path = download_release(
            self._info,
            progress_callback=lambda d, t: self.progress.emit(d, t),
        )
        self.finished.emit(path)


class UpdateAvailableDialog(QDialog):
    """Shown when a newer version is available on GitHub."""

    def __init__(self, update_info: UpdateInfo, parent=None):
        super().__init__(parent)
        self._info = update_info
        self._downloaded_path: Path | None = None
        self._ignore_version = False

        self.setWindowTitle(self.tr("Update Available"))
        self.setMinimumSize(480, 400)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Header ──────────────────────────────────────────────────
        header = QLabel(
            self.tr("<b>CuteMD {}</b> is now available (you have <b>{}</b>).").format(
                update_info.latest_tag, __import__("main").__version__
            )
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # ── Release notes ───────────────────────────────────────────
        notes_label = QLabel(self.tr("Release notes:"))
        layout.addWidget(notes_label)

        notes = QPlainTextEdit()
        notes.setPlainText(update_info.release_notes)
        notes.setReadOnly(True)
        notes.setMaximumBlockCount(500)
        layout.addWidget(notes, stretch=1)

        # ── Buttons ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self._download_btn = QPushButton(self.tr("Download"))
        self._download_btn.clicked.connect(self._on_download)
        btn_row.addWidget(self._download_btn)

        self._ignore_btn = QPushButton(self.tr("Skip this version"))
        self._ignore_btn.clicked.connect(self._on_ignore)
        btn_row.addWidget(self._ignore_btn)

        self._close_btn = QPushButton(self.tr("Later"))
        self._close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._close_btn)

        layout.addLayout(btn_row)

    def downloaded_path(self) -> Path | None:
        return self._downloaded_path

    def ignore_version(self) -> bool:
        return self._ignore_version

    def _on_download(self) -> None:
        self._download_btn.setEnabled(False)
        self._ignore_btn.setEnabled(False)
        self._close_btn.setText(self.tr("Cancel"))

        # Switch to progress layout
        layout = self.layout()
        if layout is None:
            return
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximum(0)  # indeterminate until we know total
        layout.insertWidget(layout.count() - 1, self._progress_bar)

        # Start download thread
        self._thread = _DownloadThread(self._info, self)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_download_done)
        self._close_btn.clicked.disconnect()
        self._close_btn.clicked.connect(self._on_cancel_download)
        self._thread.start()

    def _on_progress(self, downloaded: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(downloaded)

    def _on_cancel_download(self) -> None:
        if hasattr(self, "_thread") and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        self.reject()

    def _on_download_done(self, path: object) -> None:
        self._downloaded_path = path if isinstance(path, Path) else None
        if self._downloaded_path:
            self.accept()
        else:
            QMessageBox.warning(
                self,
                self.tr("Download Failed"),
                self.tr(
                    "Could not download the update. Please check your "
                    "internet connection and try again, or download "
                    "manually from the GitHub releases page."
                ),
            )
            self.reject()

    def _on_ignore(self) -> None:
        self._ignore_version = True
        self.accept()
