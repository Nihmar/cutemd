"""Zen Mode manager — hides all chrome and centers the editor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QTimer, QVariantAnimation

from core.logging import setup_logging

if TYPE_CHECKING:
    from ui.main_window import MainWindow

_LOG = setup_logging("cutemd.zen_mode_manager")


class ZenModeManager:
    """Handles enter/exit of zen mode with animated splitter transition."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window
        self._zen_saved: dict | None = None
        self._zen_anim: QVariantAnimation | None = None

    @property
    def is_active(self) -> bool:
        return self._zen_saved is not None

    def toggle(self, enabled: bool) -> None:
        if self._zen_anim is not None:
            self._zen_anim.stop()

        if enabled:
            self._enter()
        else:
            self._exit()

    def _enter(self) -> None:
        w = self._w
        self._zen_saved = {
            "left": w._side_panel.is_left_panel_open(),
            "right": w._right_splitter.isVisible(),
            "menu": w.menuBar().isVisible(),
            "status": w._status_file.parent().isVisible(),
            "preview": w._preview_visible,
            "tabs_bar": w._tabs.tabBar().isVisible(),
            "splitter_sizes": list(w._splitter.sizes()),
        }
        w._left_tb.hide()
        w._right_tb.hide()
        w._editor_toolbar.hide()
        w._tabs.tabBar().hide()
        w._status_file.parent().hide()
        w.menuBar().hide()

        if w._preview_visible:
            w._preview_visible = False
            from ui.editor_tab import EditorTab
            for i in range(w._tabs.count()):
                t = w._tabs.widget(i)
                if isinstance(t, EditorTab):
                    t.set_preview_visible(False)
            w.act_toggle_preview.setChecked(False)

        max_w = w._s.zen_mode_max_width()
        w._tabs.setMaximumWidth(max_w)

        # Animate splitter
        start = w._splitter.sizes()
        end = [0, 1, 0]
        self._zen_anim = QVariantAnimation(w)
        self._zen_anim.setDuration(200)
        self._zen_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._zen_anim.setStartValue(0.0)
        self._zen_anim.setEndValue(1.0)

        def _step(p):
            w._splitter.setSizes([
                int(start[0] + (end[0] - start[0]) * p),
                int(start[1] + (end[1] - start[1]) * p),
                int(start[2] + (end[2] - start[2]) * p),
            ])

        def _done():
            w._right_splitter.hide()
            w._side_panel._left_stack.hide()

        self._zen_anim.valueChanged.connect(_step)
        self._zen_anim.finished.connect(_done)
        self._zen_anim.start()

    def _exit(self) -> None:
        w = self._w
        saved = self._zen_saved
        if saved is None:
            return
        self._zen_saved = None

        lw, rw = saved.get("left"), saved.get("right")
        tv, sv, mv = saved.get("tabs_bar", True), saved.get("status", True), saved.get("menu", True)
        pv = saved.get("preview", True)
        sz = saved.get("splitter_sizes", [220, 726, 220])

        w._tabs.setMaximumWidth(16777215)
        ep = w._splitter.widget(1)
        if ep and ep.layout():
            ep.layout().setContentsMargins(0, 0, 0, 0)
        w._right_splitter.show()
        QTimer.singleShot(0, w._sync_right_toolbar_buttons)
        if lw:
            w._side_panel._left_stack.show()
        if tv:
            w._tabs.tabBar().show()
        if sv:
            w._status_file.parent().show()
        if mv:
            w.menuBar().show()
        if pv:
            w._preview_visible = True
            from ui.editor_tab import EditorTab
            for i in range(w._tabs.count()):
                t = w._tabs.widget(i)
                if isinstance(t, EditorTab):
                    t.set_preview_visible(True)
            w.act_toggle_preview.setChecked(True)
        w._left_tb.show()
        w._right_tb.show()
        w._editor_toolbar.show()
        w._sync_right_dock_visibility()

        # Animate splitter back
        def _do_exit_anim():
            start_sz = w._splitter.sizes()
            self._zen_anim = QVariantAnimation(w)
            self._zen_anim.setDuration(200)
            self._zen_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._zen_anim.setStartValue(0.0)
            self._zen_anim.setEndValue(1.0)

            def _step2(p):
                w._splitter.setSizes([
                    int(start_sz[0] + (sz[0] - start_sz[0]) * p),
                    int(start_sz[1] + (sz[1] - start_sz[1]) * p),
                    int(start_sz[2] + (sz[2] - start_sz[2]) * p),
                ])
            self._zen_anim.valueChanged.connect(_step2)
            self._zen_anim.start()

        QTimer.singleShot(0, _do_exit_anim)
