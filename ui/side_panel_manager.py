"""Side-panel manager — sidebar animations, toggle logic, TOC rebuild.

Extracted from MainWindow to reduce its size and isolate panel
animation / state management.  Manages both left and right docked
panels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QTimer, QVariantAnimation
from PySide6.QtWidgets import QDockWidget, QSplitter, QStackedWidget, QToolButton

from core.animation_speed import animation_duration_ms
from core.logging import setup_logging

if TYPE_CHECKING:
    from ui.main_window import MainWindow

_LOG = setup_logging("cutemd.side_panel")


class SidePanelManager:
    """Manages left and right side panels and their animations."""

    def __init__(
        self,
        window: MainWindow,
        splitter: QSplitter,
        left_stack: QStackedWidget,
        side_tree_btn: QToolButton,
        side_search_btn: QToolButton,
        side_toc_btn: QToolButton,
        side_tags_btn: QToolButton,
        side_tasks_btn: QToolButton,
        right_dock: QDockWidget | None = None,
    ) -> None:
        self._w = window
        self._splitter = splitter
        self._left_stack = left_stack
        self._side_tree_btn = side_tree_btn
        self._side_search_btn = side_search_btn
        self._side_toc_btn = side_toc_btn
        self._side_tags_btn = side_tags_btn
        self._side_tasks_btn = side_tasks_btn
        self._right_dock = right_dock

        self._tree_anim: QVariantAnimation | None = None
        self._save_allowed = True
        self._save_timer: QTimer | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def show_left_panel(self) -> None:
        _LOG.debug("show_left_panel")
        self._left_stack.show()
        total = self._splitter.width()
        left = self._w._s.left_panel_width()
        _LOG.debug("show_left_panel: total=%d saved_left=%d", total, left)
        if total > 0:
            self._animate_splitter_to(left)
        else:
            self._animate_splitter_to(220)

    def hide_left_panel(self) -> None:
        _LOG.debug("hide_left_panel")
        self._animate_splitter_to(0, on_finish=lambda: self._left_stack.hide())

    def is_left_panel_open(self) -> bool:
        sizes = self._splitter.sizes()
        return len(sizes) > 0 and sizes[0] > 0

    def restore_panel_width(self) -> None:
        left = self._w._s.left_panel_width()
        total = self._splitter.width()
        _LOG.debug("restore_panel_width: left=%d total=%d", left, total)
        if total > 0 and left >= 0:
            left = max(0, min(left, total))
            sizes = self._splitter.sizes()
            right = sizes[2] if len(sizes) > 2 else 0
            mid = max(total - left - right, 0)
            self._splitter.setSizes([left, mid, right])
        self._reset_save_timer()

    # ------------------------------------------------------------------
    # Side-button toggle handlers (mutually exclusive group)
    # ------------------------------------------------------------------

    def on_tree_toggled(self, checked: bool) -> None:
        if checked:
            self._uncheck_others(self._side_tree_btn)
            self._left_stack.setCurrentIndex(0)
            if not self.is_left_panel_open():
                self.show_left_panel()
        else:
            self.hide_left_panel()

    def on_search_toggled(self, checked: bool) -> None:
        if checked:
            self._uncheck_others(self._side_search_btn)
            self._left_stack.setCurrentIndex(1)
            if not self.is_left_panel_open():
                self.show_left_panel()
            self._w._search_panel._search_input.setFocus()
        else:
            self.hide_left_panel()

    def on_toc_toggled(self, checked: bool) -> None:
        """Toggle the right dock (TOC panel).  Independent of left panels."""
        if self._right_dock is not None:
            self._right_dock.setVisible(checked)
            if checked:
                self._w._rebuild_toc()
            else:
                self._w._toc_timer.stop()

    def on_tree_action(self, visible: bool) -> None:
        """Handle the act_toggle_tree action (from menu / shortcut)."""
        if visible:
            self._uncheck_others(self._side_tree_btn)
            self._left_stack.setCurrentIndex(0)
            self.show_left_panel()
        else:
            self._side_tree_btn.setChecked(False)
            self._side_search_btn.setChecked(False)
            self._side_tags_btn.setChecked(False)
            self.hide_left_panel()
            # Also hide right dock
            if self._right_dock is not None:
                self._right_dock.setVisible(False)
                self._side_toc_btn.setChecked(False)

    def hide_all_panels(self) -> None:
        """Called when closing a folder — hide everything."""
        self._uncheck_others(None)
        self._left_stack.hide()
        if self._right_dock is not None:
            self._right_dock.setVisible(False)
            self._side_toc_btn.setChecked(False)

    def open_search_panel(self) -> None:
        """Show the search panel in the left stack."""
        if self._left_stack.currentIndex() == 1 and not self._left_stack.isHidden():
            self._uncheck_others(None)
            self.hide_left_panel()
        else:
            self._uncheck_others(self._side_search_btn)
            self._left_stack.setCurrentIndex(1)
            self.show_left_panel()
            self._w._search_panel._search_input.setFocus()
            self._w._search_panel._search_input.selectAll()

    def open_replace_panel(self) -> None:
        """Show the replace panel in the left stack."""
        if self._left_stack.currentIndex() == 1 and not self._left_stack.isHidden():
            self._w._search_panel._replace_input.setFocus()
            self._w._search_panel._replace_input.selectAll()
        else:
            self._uncheck_others(self._side_search_btn)
            self._left_stack.setCurrentIndex(1)
            self.show_left_panel()
            self._w._search_panel._replace_input.setFocus()
            self._w._search_panel._replace_input.selectAll()

    # ------------------------------------------------------------------
    # Splitter animation
    # ------------------------------------------------------------------

    def _animate_splitter_to(self, left_width: int, on_finish=None) -> None:
        total = self._splitter.width()
        _LOG.debug("_animate_splitter_to: left=%d total=%d", left_width, total)
        if total <= 0:
            if on_finish:
                on_finish()
            return

        if self._tree_anim is not None:
            self._tree_anim.stop()
        sizes = self._splitter.sizes()
        start = sizes[0] if len(sizes) > 0 else 0
        right = sizes[2] if len(sizes) > 2 else 0

        if start == left_width:
            if on_finish:
                on_finish()
            return

        self._tree_anim = QVariantAnimation(self._w)
        self._tree_anim.setDuration(animation_duration_ms(150))
        self._tree_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._tree_anim.setStartValue(0.0)
        self._tree_anim.setEndValue(1.0)

        def _step(progress: float) -> None:
            cur = int(start + (left_width - start) * progress)
            sizes = self._splitter.sizes()
            right = sizes[2] if len(sizes) > 2 else 0
            mid = max(total - cur - right, 0)
            self._splitter.setSizes([max(cur, 0), mid, right])

        self._tree_anim.valueChanged.connect(_step)

        def _done() -> None:
            self._reset_save_timer()
            if on_finish:
                on_finish()

        self._tree_anim.finished.connect(_done)
        self._tree_anim.start()

    def _reset_save_timer(self) -> None:
        """Ignore splitterMoved for 500ms after programmatic setSizes."""
        self._save_allowed = False
        if self._save_timer is not None:
            self._save_timer.stop()
        self._save_timer = QTimer(self._w)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._allow_save)
        self._save_timer.start(500)

    def _allow_save(self) -> None:
        self._save_allowed = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _uncheck_others(self, active: QToolButton | None) -> None:
        """Uncheck left-panel buttons (tree, search, tags, tasks), then re-check
        *active* if given.  TOC is independent and not touched here.

        Signals are blocked during the operation to prevent infinite
        recursion from the toggle handlers that call this method.
        """
        for btn in [self._side_tree_btn, self._side_search_btn, self._side_tags_btn, self._side_tasks_btn]:
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        if active is not None:
            active.blockSignals(True)
            active.setChecked(True)
            active.blockSignals(False)
