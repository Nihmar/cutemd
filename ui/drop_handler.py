"""Drag-and-drop / clipboard-paste handler for the editor.

Extracted from EditorTab to keep the tab class focused.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from core.constants import IMG_EXTS
from core.logging import setup_logging

if TYPE_CHECKING:
    from ui.editor_tab import EditorTab

_LOG = setup_logging("cutemd.drop_handler")


class DropHandler:
    """Handles file drops and clipboard paste in the editor viewport."""

    def __init__(self, tab: EditorTab) -> None:
        self._tab = tab
        self._drag_active = False

    @property
    def drag_active(self) -> bool:
        return self._drag_active

    # ------------------------------------------------------------------
    # Drag-and-drop events
    # ------------------------------------------------------------------

    def on_drag_enter(self, event) -> None:
        self._drag_active = False
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    self._drag_active = True
                    event.acceptProposedAction()
                    return
        event.ignore()

    def on_drop(self, event) -> bool:
        """Handle dropped files. Returns True if any file was handled."""
        if not event.mimeData().hasUrls():
            return False
        handled = False
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_file() and self._handle_file_drop(path):
                    handled = True
        if handled:
            event.acceptProposedAction()
        else:
            event.ignore()
        return handled

    # ------------------------------------------------------------------
    # Clipboard paste (Ctrl+V with image / file)
    # ------------------------------------------------------------------

    def paste_from_clipboard(self) -> bool:
        """Paste clipboard content: file URLs or bitmap image.
        Returns True if handled."""
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False

        # 1) Try file URLs first (copy from Explorer / file manager)
        mime = clipboard.mimeData()
        if mime is not None and mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_file() and self._handle_file_drop(path):
                        return True

        # 2) Try bitmap data (copy from browser / screenshot)
        img = clipboard.image()
        if not img.isNull():
            attachments_dir = self._tab._attachments_dir
            if attachments_dir is None:
                return False
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"paste_{ts}.png"
            dest = attachments_dir / filename
            attachments_dir.mkdir(parents=True, exist_ok=True)
            if not img.save(str(dest), "PNG"):
                return False
            return self._handle_file_drop(dest)

        return False

    # ------------------------------------------------------------------
    # Internal: file → link insertion
    # ------------------------------------------------------------------

    def _handle_file_drop(self, path: Path) -> bool:
        """Copy *path* to the attachments dir and insert a link."""
        tab = self._tab
        vault_root = (
            tab._attachments_dir.parent.resolve()
            if tab._attachments_dir
            else None
        )

        # If the file is already inside the vault, link it in-place.
        if vault_root is not None:
            try:
                path.resolve().relative_to(vault_root)
                _LOG.debug("in-vault file — linking in-place %s", path.name)
                return self._insert_file_link(path)
            except ValueError:
                pass

        # Otherwise copy to the attachments directory.
        dest_dir = tab._attachments_dir
        if dest_dir is None:
            base = tab._file_path.parent if tab._file_path else Path.cwd()
            dest_dir = base / "attachments"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        if dest.exists():
            stem, ext = path.stem, path.suffix
            n = 1
            while dest.exists():
                dest = dest_dir / f"{stem}_{n}{ext}"
                n += 1

        try:
            if dest.resolve() != path.resolve():
                shutil.copy2(str(path), str(dest))
        except OSError:
            return False
        return self._insert_file_link(dest)

    def _insert_file_link(self, dest: Path) -> bool:
        """Insert a markdown or wikilink for *dest*."""
        tab = self._tab
        link = None

        if tab._attachments_dir is not None:
            try:
                dest.resolve().relative_to(tab._attachments_dir.resolve())
                link = dest.name
            except ValueError:
                pass

        if link is None and tab._file_path and tab._file_path.parent:
            try:
                rel = dest.resolve().relative_to(
                    tab._file_path.parent.resolve(), walk_up=True
                )
                link = rel.as_posix()
            except ValueError:
                pass

        if link is None:
            link = dest.as_posix()

        is_image = dest.suffix.lower() in IMG_EXTS
        if tab._link_style == "wiki":
            syntax = f"![[{link}]]" if is_image else f"[[{link}]]"
        else:
            syntax = (
                f"![{dest.stem}]({link})" if is_image
                else f"[{dest.stem}]({link})"
            )

        cursor = tab.editor.textCursor()
        cursor.insertText(syntax)
        tab.editor.setFocus()
        return True
