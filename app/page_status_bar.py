from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QSizeGrip, QStatusBar, QWidget


STATUS_BAR_HEIGHT = 29


class PageStatusBar(QStatusBar):
    """Full-width host for optional page-specific status controls."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._controls: dict[str, QWidget] = {}
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._layout_controls)
        self.setFixedHeight(STATUS_BAR_HEIGHT)

    def register_control(self, page_name, control):
        page_name = str(page_name)

        if page_name in self._controls:
            raise ValueError(
                f"Status control already registered for {page_name!r}"
            )

        control.setParent(self)
        control.hide()
        self._controls[page_name] = control
        self._layout_controls()

    def set_active_control(self, page_name):
        for name, control in self._controls.items():
            control.setVisible(name == page_name)

        self._layout_controls()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_controls()
        self._layout_timer.start(0)

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_controls()
        self._layout_timer.start(0)

    def _layout_controls(self):
        available_width = self.width()
        size_grip = self.findChild(QSizeGrip)

        if size_grip is not None and size_grip.isVisible():
            grip_width = size_grip.width()

            if not 0 < grip_width < self.width():
                grip_width = max(0, size_grip.sizeHint().width())

            available_width = self.width() - grip_width

        if available_width <= 0 and self.width() > 0:
            available_width = self.width()

        for control in self._controls.values():
            control.setGeometry(
                0,
                0,
                max(0, available_width),
                self.height(),
            )

            if control.isVisible():
                control.raise_()

        if size_grip is not None:
            size_grip.raise_()
