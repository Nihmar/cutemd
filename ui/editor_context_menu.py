"""Editor context menu — right-click formatting actions."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QIcon, QKeySequence, QTextCursor
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget

from core.markdown_actions import CONTEXT_MENU_ITEMS


def show_editor_context_menu(
    parent: QWidget,
    point: QPoint,
    icon_color: QColor,
    make_icon: Callable[[str, QColor, int], QIcon],
    on_format: Callable[[str], None],
    on_image: Callable[[], None],
    spell_checker=None,
    on_add_to_dict: Callable[[str], None] | None = None,
) -> None:
    """Build and show the right-click formatting menu for the editor."""
    sender = parent.sender()
    if not isinstance(sender, QPlainTextEdit):
        return

    menu = QMenu(parent)
    ic = icon_color

    def _icon(name: str) -> QIcon:
        return make_icon(name, ic, 18)

    # --- Edit actions ---
    has_selection = sender.textCursor().hasSelection()

    act_undo = menu.addAction(_icon("undo"), parent.tr("&Undo"))
    act_undo.setShortcut(QKeySequence.StandardKey.Undo)
    act_undo.setEnabled(sender.isUndoRedoEnabled() and sender.document().isUndoAvailable())
    act_undo.triggered.connect(sender.undo)

    act_redo = menu.addAction(_icon("redo"), parent.tr("&Redo"))
    act_redo.setShortcut(QKeySequence.StandardKey.Redo)
    act_redo.setEnabled(sender.isUndoRedoEnabled() and sender.document().isRedoAvailable())
    act_redo.triggered.connect(sender.redo)

    menu.addSeparator()

    act_cut = menu.addAction(_icon("cut"), parent.tr("Cu&t"))
    act_cut.setShortcut(QKeySequence.StandardKey.Cut)
    act_cut.setEnabled(has_selection)
    act_cut.triggered.connect(sender.cut)

    act_copy = menu.addAction(_icon("copy"), parent.tr("&Copy"))
    act_copy.setShortcut(QKeySequence.StandardKey.Copy)
    act_copy.setEnabled(has_selection)
    act_copy.triggered.connect(sender.copy)

    act_paste = menu.addAction(_icon("paste"), parent.tr("&Paste"))
    act_paste.setShortcut(QKeySequence.StandardKey.Paste)
    act_paste.triggered.connect(sender.paste)

    act_delete = menu.addAction(_icon("delete"), parent.tr("&Delete"))
    act_delete.setShortcut(QKeySequence.StandardKey.Delete)
    act_delete.setEnabled(has_selection)
    act_delete.triggered.connect(
        lambda: sender.textCursor().removeSelectedText()
    )

    menu.addSeparator()

    # --- Formatting submenus ---
    categories: dict[str, tuple[QMenu, QIcon, str]] = {}

    for category, icon_name, label, syntax in CONTEXT_MENU_ITEMS:
        if category not in categories:
            cat_icon = _icon(icon_name)
            if category == "inline":
                cat_menu = menu.addMenu(parent.tr("Inline &Formatting"))
            elif category == "list":
                cat_menu = menu.addMenu(parent.tr("&Lists"))
            elif category == "block":
                cat_menu = menu.addMenu(parent.tr("&Blocks"))
            else:
                cat_menu = menu.addMenu(parent.tr("&Insert"))
            cat_menu.setIcon(cat_icon)
            categories[category] = (cat_menu, cat_icon, category)

        submenu, sub_icon, _cat = categories[category]
        action = submenu.addAction(_icon(icon_name), parent.tr(label))
        action.triggered.connect(lambda checked=False, s=syntax: on_format(s))

    # Image is handled separately in the Insert menu
    insert_menu = categories.get("insert", (None, None, ""))[0]
    if insert_menu:
        insert_menu.addAction(_icon("image"), parent.tr("&Image")).triggered.connect(on_image)

    # Spell-check suggestions
    if spell_checker is not None and getattr(spell_checker, "available", False):
        cursor = sender.cursorForPosition(point)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText()
        if word and len(word) >= 3 and not spell_checker.check(word):
            # Save cursor position for replacement
            saved_cursor = QTextCursor(cursor)
            saved_cursor.setPosition(cursor.selectionStart())
            saved_cursor.setPosition(cursor.selectionEnd(), QTextCursor.MoveMode.KeepAnchor)

            menu.addSeparator()
            suggestions = spell_checker.suggest(word)
            if suggestions:
                for s in suggestions[:8]:
                    action = menu.addAction(s)
                    action.triggered.connect(
                        lambda checked=False, sug=s, sc=saved_cursor, ed=sender:
                        _replace_word(ed, sc, sug)
                    )
            else:
                menu.addAction(parent.tr("(no suggestions)")).setEnabled(False)
            # Add-to-dictionary action
            if on_add_to_dict is not None:
                act = menu.addAction(parent.tr("Add to dictionary"))
                act.triggered.connect(
                    lambda checked=False, w=word: on_add_to_dict(w)
                )

    menu.exec(sender.viewport().mapToGlobal(point))


def _replace_word(editor: QPlainTextEdit, saved_cursor: QTextCursor, new: str) -> None:
    """Replace the word at *saved_cursor* position with *new*."""
    editor.setTextCursor(saved_cursor)
    saved_cursor.insertText(new)
