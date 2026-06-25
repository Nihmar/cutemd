"""Shared custom widgets with consistent defaults."""

from PySide6.QtWidgets import QListWidget


class CuteListWidget(QListWidget):
    """QListWidget with a comfortable default inter-item spacing."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setSpacing(6)
