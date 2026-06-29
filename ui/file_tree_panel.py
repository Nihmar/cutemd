"""Folder tree panel --- shows markdown files in a QTreeView."""

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QSize, QSortFilterProxyModel, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileSystemModel,
    QInputDialog,
    QMenu,
    QMessageBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from core.logging import setup_logging
from core.trash import permanent_delete as trash_permanent_delete
from core.trash import trash_file

_LOG = setup_logging("cutemd.file_tree")


class _FileTreeView(QTreeView):
    """Custom tree view with keyboard shortcuts and drag-drop support."""

    file_rename_requested = Signal(str)
    file_delete_requested = Signal(str)
    files_dropped = Signal(list, str)  # (source_paths, target_dir)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def _source_model(self):
        p = self.model()
        return p.sourceModel() if isinstance(p, QSortFilterProxyModel) else p

    def _file_path(self, index):
        p = self.model()
        if isinstance(p, QSortFilterProxyModel):
            return p.sourceModel().filePath(p.mapToSource(index))
        return p.filePath(index)

    def _root_path(self):
        p = self.model()
        if isinstance(p, QSortFilterProxyModel):
            return p.sourceModel().rootPath()
        return p.rootPath()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F2:
            index = self.currentIndex()
            if index.isValid():
                path = self._file_path(index)
                if path:
                    self.file_rename_requested.emit(path)
            return
        if event.key() == Qt.Key.Key_Delete:
            for index in self.selectionModel().selectedRows():
                path = self._file_path(index)
                if path:
                    self.file_delete_requested.emit(path)
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.source() == self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.source() != self:
            event.ignore()
            return
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            path = self._file_path(index)
            if path and Path(path).is_dir():
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """Resolve the drop target path and emit ``files_dropped``.

        If the drop lands on a folder index, that folder becomes the target.
        If it lands on a file, the file's parent directory is used instead.
        When the drop position does not hit any index, the tree's root path
        is used as the fallback target directory.
        """
        if event.source() != self:
            event.ignore()
            return

        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            path = self._file_path(index)
            if path:
                target_dir = str(Path(path) if Path(path).is_dir() else Path(path).parent)
            else:
                target_dir = self._root_path()
        else:
            target_dir = self._root_path()

        if not target_dir:
            event.ignore()
            return

        urls = event.mimeData().urls()
        source_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]

        if not source_paths:
            event.ignore()
            return

        self.files_dropped.emit(source_paths, target_dir)
        event.acceptProposedAction()


class _DotFileFilterProxy(QSortFilterProxyModel):
    """Hides files and folders whose name starts with '.' when disabled."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._show_hidden = False

    def set_show_hidden(self, show: bool) -> None:
        if self._show_hidden != show:
            self._show_hidden = show
            self.invalidateFilter()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.ToolTipRole:
            src_idx = self.mapToSource(index)
            return self.sourceModel().fileName(src_idx)
        return super().data(index, role)

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if self._show_hidden:
            return True
        model = self.sourceModel()
        if model is None:
            return True
        idx = model.index(source_row, 0, source_parent)
        name = model.fileName(idx)
        if name.startswith("."):
            return False
        return True


class FileTreePanel(QWidget):
    """Sidebar widget that displays a tree of markdown files under a root folder.

    Emits:
        file_activated(str) --- absolute path of the file the user clicked.
        file_double_activated(str) --- absolute path of the file the user double-clicked.
        file_open_new_tab(str) --- open file in a new tab unconditionally.
        file_renamed(str, str) --- (old_path, new_path) after a rename.
        file_deleted(str) --- path of a deleted file.
    """

    file_activated = Signal(str)
    file_double_activated = Signal(str)
    file_open_new_tab = Signal(str)
    file_renamed = Signal(str, str)
    file_deleted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._trash_enabled = False
        self._vault_root: Path | None = None

        self._model = QFileSystemModel()
        self._model.setReadOnly(True)
        self._model.setFilter(
            QDir.Filter.Files | QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot
        )

        self._proxy = _DotFileFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._tree = _FileTreeView()
        self._tree.setModel(self._proxy)
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.setIconSize(QSize(16, 16))
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Show only the file name column
        for col in range(1, self._model.columnCount()):
            self._tree.hideColumn(col)

        self._tree.clicked.connect(self._on_activated)
        self._tree.doubleClicked.connect(self._on_double_activated)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.file_rename_requested.connect(self._rename_item)
        self._tree.file_delete_requested.connect(self._delete_item)
        self._tree.files_dropped.connect(self._move_items)

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
        _LOG.debug("set_root_path: %s", path)
        p = Path(path)
        if not p.is_dir():
            self._model.setRootPath("")
            self._tree.setRootIndex(self._proxy.mapFromSource(self._model.index("")))
            return
        root = str(p.resolve())
        src_idx = self._model.setRootPath(root)
        self._tree.setRootIndex(self._proxy.mapFromSource(src_idx))

    def select_file(self, path: str | Path) -> None:
        """Highlight *path* in the tree without stealing focus."""
        idx = self._model.index(str(Path(path).resolve()))
        if idx.isValid():
            proxy_idx = self._proxy.mapFromSource(idx)
            # Use selection model instead of setCurrentIndex to avoid
            # stealing focus from the editor on every save.
            from PySide6.QtCore import QItemSelectionModel
            self._tree.selectionModel().select(
                proxy_idx,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            self._tree.scrollTo(proxy_idx)

    def root_path(self) -> str:
        """Return the current root path (or empty string if none)."""
        return self._model.rootPath()

    def set_show_hidden_files(self, show: bool) -> None:
        self._proxy.set_show_hidden(show)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_activated(self, index) -> None:
        src_idx = self._proxy.mapToSource(index)
        path = self._model.filePath(src_idx)
        _LOG.debug("_on_activated: %s", path)
        if path and Path(path).is_file():
            self.file_activated.emit(path)

    def _on_double_activated(self, index) -> None:
        src_idx = self._proxy.mapToSource(index)
        path = self._model.filePath(src_idx)
        _LOG.debug("_on_double_activated: %s", path)
        if path and Path(path).is_file():
            self.file_double_activated.emit(path)

    def _open_path(self, path_str: str) -> None:
        """Open *path_str* in the system file manager / default application."""
        _LOG.debug("_open_path: %s", path_str)
        url = QUrl.fromLocalFile(path_str)
        if not QDesktopServices.openUrl(url):
            _LOG.debug("QDesktopServices.openUrl returned False, trying xdg-open")
            if sys.platform == "linux":
                subprocess.Popen(["xdg-open", path_str])

    def _on_context_menu(self, point) -> None:
        _LOG.debug("_on_context_menu")
        index = self._tree.indexAt(point)
        if not index.isValid():
            return

        src_idx = self._proxy.mapToSource(index)
        path = self._model.filePath(src_idx)
        if not path:
            return

        p = Path(path)
        menu = QMenu(self._tree)

        if p.is_dir():
            act_rename = menu.addAction(self.tr("Rename"))
            act_rename.triggered.connect(lambda: self._rename_item(str(p)))
            act_delete = menu.addAction(self.tr("Delete"))
            act_delete.triggered.connect(lambda: self._delete_item(str(p)))
            menu.addSeparator()
            act_explorer = menu.addAction(self.tr("Open in file explorer"))
            act_explorer.triggered.connect(
                lambda: self._open_path(path)
            )
        else:
            act_new_tab = menu.addAction(self.tr("Open in new tab"))
            act_new_tab.triggered.connect(lambda: self.file_open_new_tab.emit(str(p)))
            menu.addSeparator()
            act_rename = menu.addAction(self.tr("Rename"))
            act_rename.triggered.connect(lambda: self._rename_item(str(p)))
            act_duplicate = menu.addAction(self.tr("Duplicate"))
            act_duplicate.triggered.connect(lambda: self._duplicate_file(str(p)))
            act_delete = menu.addAction(self.tr("Delete"))
            act_delete.triggered.connect(lambda: self._delete_item(str(p)))
            menu.addSeparator()
            act_open = menu.addAction(self.tr("Open with default application"))
            act_open.triggered.connect(
                lambda: self._open_path(path)
            )
            act_explorer = menu.addAction(self.tr("Open in file explorer"))
            act_explorer.triggered.connect(
                lambda: self._open_path(str(p.parent))
            )
            menu.addSeparator()
            act_copy = menu.addAction(self.tr("Copy location"))
            act_copy.triggered.connect(
                lambda fp=str(p.resolve()): QApplication.clipboard().setText(fp)
            )

        menu.exec(self._tree.viewport().mapToGlobal(point))

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def _rename_item(self, path_str: str) -> None:
        p = Path(path_str)
        new_name, ok = QInputDialog.getText(
            self, self.tr("Rename"), self.tr("New name:"),
            text=p.name,
        )
        if not ok or not new_name.strip() or new_name.strip() == p.name:
            return
        new_path = p.with_name(new_name.strip())
        if new_path.exists():
            QMessageBox.warning(
                self, self.tr("Rename"),
                self.tr("A file or folder with that name already exists."),
            )
            return
        try:
            p.rename(new_path)
            _LOG.debug("_on_file_renamed: old=%s new=%s", path_str, str(new_path))
            self.file_renamed.emit(str(p), str(new_path))
        except OSError as e:
            QMessageBox.critical(
                self, self.tr("Error"),
                self.tr("Could not rename:\n{}").format(e),
            )

    def _duplicate_file(self, path_str: str) -> None:
        p = Path(path_str)
        stem = p.stem
        ext = p.suffix
        n = 1
        while True:
            suffix = f" ({n})" if n > 1 else " (copy)"
            new_name = f"{stem}{suffix}{ext}"
            new_path = p.with_name(new_name)
            if not new_path.exists():
                break
            n += 1
        try:
            shutil.copy2(str(p), str(new_path))
        except OSError as e:
            QMessageBox.critical(
                self, self.tr("Error"),
                self.tr("Could not duplicate:\n{}").format(e),
            )

    def set_trash_config(self, enabled: bool, vault_root: Path | None) -> None:
        self._trash_enabled = enabled
        self._vault_root = vault_root

    def _delete_item(self, path_str: str) -> None:
        p = Path(path_str)
        is_dir = p.is_dir()
        if self._trash_enabled and self._vault_root is not None and not is_dir:
            # Single files go to trash
            msg = self.tr("Move '{}' to trash?").format(p.name)
        elif is_dir:
            msg = self.tr("Delete folder '{}' and all its contents?").format(p.name)
        else:
            msg = self.tr("Delete '{}'?").format(p.name)
        ret = QMessageBox.question(
            self, self.tr("Delete"), msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            if self._trash_enabled and self._vault_root is not None and not is_dir:
                trash_file(p, self._vault_root)
            elif is_dir:
                shutil.rmtree(p)
            else:
                p.unlink()
            _LOG.debug("_on_file_deleted: %s", path_str)
            self.file_deleted.emit(str(p))
        except OSError as e:
            QMessageBox.critical(
                self, self.tr("Error"),
                self.tr("Could not delete:\n{}").format(e),
            )

    def _move_items(self, source_paths: list[str], target_dir: str) -> None:
        """Perform a drag-drop move of files/folders into *target_dir*.

        If the destination already contains an item with the same name, the user
        is asked whether to overwrite it (overwritten items are deleted first).
        After each successful move, ``file_renamed`` is emitted so that listeners
        (e.g. open editor tabs) can update their paths.
        """
        _LOG.debug("_move_items")
        dest = Path(target_dir)
        moved_old_new = []
        for sp in source_paths:
            src = Path(sp)
            if src.parent == dest:
                continue
            new_path = dest / src.name
            if new_path.exists():
                ret = QMessageBox.question(
                    self, self.tr("Overwrite"),
                    self.tr("'{}' already exists. Overwrite?").format(new_path.name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ret != QMessageBox.StandardButton.Yes:
                    continue
                try:
                    if new_path.is_dir():
                        shutil.rmtree(new_path)
                    else:
                        new_path.unlink()
                except OSError as e:
                    QMessageBox.critical(
                        self, self.tr("Error"),
                        self.tr("Could not overwrite '{}':\n{}").format(new_path.name, e),
                    )
                    continue
            try:
                shutil.move(str(src), str(new_path))
                moved_old_new.append((sp, str(new_path)))
            except OSError as e:
                QMessageBox.critical(
                    self, self.tr("Error"),
                    self.tr("Could not move '{}':\n{}").format(src.name, e),
                )

        for old_path, new_path in moved_old_new:
            self.file_renamed.emit(old_path, new_path)
