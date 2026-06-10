"""Folder tree panel --- shows markdown files in a QTreeView."""

from pathlib import Path

from PySide6.QtCore import QDir, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileSystemModel,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class FileTreePanel(QWidget):
    """Sidebar widget that displays a tree of markdown files under a root folder.

    Emits:
        file_activated(str) --- absolute path of the file the user clicked.
    """

    file_activated = Signal(str)
    file_open_new_tab = Signal(str)

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
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Show only the file name column
        for col in range(1, self._model.columnCount()):
            self._tree.hideColumn(col)

        self._tree.clicked.connect(self._on_activated)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

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

    def _on_context_menu(self, point) -> None:
        index = self._tree.indexAt(point)
        if not index.isValid():
            return

        path = self._model.filePath(index)
        if not path:
            return

        p = Path(path)
        menu = QMenu(self._tree)

        if p.is_dir():
            act_explorer = menu.addAction(self.tr("Open in file explorer"))
            act_explorer.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
            )
        else:
            act_new_tab = menu.addAction(self.tr("Open in new tab"))
            act_new_tab.triggered.connect(lambda: self.file_open_new_tab.emit(str(p)))
            menu.addSeparator()
            act_open = menu.addAction(self.tr("Open with default application"))
            act_open.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
            )
            act_explorer = menu.addAction(self.tr("Open in file explorer"))
            act_explorer.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))
            )

        menu.exec(self._tree.viewport().mapToGlobal(point))
