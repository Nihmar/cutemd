"""Folder tree panel — shows markdown files in a QTreeView."""

from pathlib import Path

from PySide6.QtCore import QDir, Qt, Signal
from PySide6.QtWidgets import QFileSystemModel, QTreeView, QVBoxLayout, QWidget


class FileTreePanel(QWidget):
    """Sidebar widget that displays a tree of markdown files under a root folder.

    Emits:
        file_activated(str) — absolute path of the file the user clicked.
    """

    file_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._model = QFileSystemModel()
        self._model.setReadOnly(True)
        self._model.setFilter(
            QDir.Filter.Files | QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot
        )
        self._model.setNameFilters(["*.md", "*.markdown"])
        self._model.setNameFilterDisables(False)

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Show only the file name column
        for col in range(1, self._model.columnCount()):
            self._tree.hideColumn(col)

        self._tree.clicked.connect(self._on_activated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_root_path(self, path: str | Path) -> None:
        """Point the tree at *path* and expand its root.

        Pass an empty string to clear the tree.
        """
        p = Path(path)
        if not p.is_dir():
            self._model.setRootPath("")
            self._tree.setRootIndex(self._model.index(""))
            return
        root = str(p.resolve())
        idx = self._model.setRootPath(root)
        self._tree.setRootIndex(idx)

    def select_file(self, path: str | Path) -> None:
        """Highlight *path* in the tree."""
        idx = self._model.index(str(Path(path).resolve()))
        if idx.isValid():
            self._tree.setCurrentIndex(idx)

    def root_path(self) -> str:
        """Return the current root path (or empty string if none)."""
        return self._model.rootPath()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_activated(self, index) -> None:
        path = self._model.filePath(index)
        if path and Path(path).is_file():
            self.file_activated.emit(path)
