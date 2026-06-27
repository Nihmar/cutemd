"""WebDAV synchronisation — Qt thread bridge.

Pure logic (sync engine, HTTP client, data models) lives in
``core.webdav.sync``.  This module only provides the ``SyncThread``
QThread wrapper.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, Signal

from core.webdav.sync import SyncResult, backup_vault, sync_folder


class SyncThread(QThread):
    """QThread that runs ``sync_folder()`` in the background."""

    progress = Signal(str)
    finished = Signal(object)

    def __init__(
        self, local_root: Path, url: str, username: str, password: str
    ) -> None:
        super().__init__()
        self._local_root = local_root
        self._url = url
        self._username = username
        self._password = password

    def run(self) -> None:
        result = sync_folder(
            self._local_root,
            self._url,
            self._username,
            self._password,
            progress_callback=lambda msg: self.progress.emit(msg),
            translate=QCoreApplication.translate,
        )
        self.finished.emit(result)


class BackupThread(QThread):
    """QThread that runs ``backup_vault()`` in the background."""

    progress = Signal(str)
    finished = Signal(object)  # str (backup path) or None

    def __init__(self, vault_path: Path, backup_dir: str) -> None:
        super().__init__()
        self._vault_path = vault_path
        self._backup_dir = backup_dir

    def run(self) -> None:
        result = backup_vault(
            self._vault_path,
            self._backup_dir,
            progress_callback=lambda msg: self.progress.emit(msg),
        )
        self.finished.emit(result)
