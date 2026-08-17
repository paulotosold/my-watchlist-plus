from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from app.paths import ICONS_DIR

STATUS_ICON_SIZE = 20
STATUS_BUTTON_SIZE = 24
STATUS_BUTTON_RADIUS = STATUS_BUTTON_SIZE // 2
STATUS_BUTTON_HOVER_BACKGROUND = "rgba(0, 0, 0, 18)"
STATUS_BAR_ICON_DIR = ICONS_DIR / "status_bar"
ICON_BUTTON_STYLE = f"""
QToolButton {{
    background: transparent;
    border: none;
    border-radius: {STATUS_BUTTON_RADIUS}px;
    padding: 0;
}}
QToolButton:hover {{
    background: {STATUS_BUTTON_HOVER_BACKGROUND};
}}
QToolButton:disabled {{
    background: transparent;
    border: none;
    color: #8a8a8a;
}}
"""


class PostersPerRowControl(QWidget):
    """Status-bar control expressing grid density as poster size."""

    value_changed = Signal(int)

    def __init__(
        self,
        parent=None,
        *,
        value,
        minimum,
        maximum,
    ):
        super().__init__(parent)

        self._minimum = int(minimum)
        self._maximum = int(maximum)
        if self._minimum > self._maximum:
            raise ValueError("minimum cannot be greater than maximum")

        self.setObjectName("postersPerRowControl")
        self._value = self._clamp(value)

        self.title_label = QLabel("Poster size", self)
        self.title_label.setObjectName("posterSizeLabel")

        self.minus_button = self._make_button(
            "poster_smaller.png",
            object_name="decreasePosterSizeButton",
            accessible_name="Decrease poster size",
            tooltip="Decrease poster size (show more posters per row)",
        )
        self.plus_button = self._make_button(
            "poster_larger.png",
            object_name="increasePosterSizeButton",
            accessible_name="Increase poster size",
            tooltip="Increase poster size (show fewer posters per row)",
        )

        # Compatibility aliases use the visual poster-size semantics.
        self.decrease_button = self.minus_button
        self.increase_button = self.plus_button

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.minus_button)
        layout.addWidget(self.plus_button)

        self.minus_button.clicked.connect(self.increment)
        self.plus_button.clicked.connect(self.decrement)
        self._update_accessible_value()
        self._update_button_states()

    def value(self):
        return self._value

    @property
    def posters_per_row(self):
        return self._value

    @property
    def minimum(self):
        return self._minimum

    @property
    def maximum(self):
        return self._maximum

    def set_value(self, value):
        clamped_value = self._clamp(value)

        if clamped_value == self._value:
            self._update_button_states()
            return

        self._value = clamped_value
        self._update_accessible_value()
        self._update_button_states()
        self.value_changed.emit(self._value)

    def decrement(self):
        self.set_value(self._value - 1)

    def increment(self):
        self.set_value(self._value + 1)

    def _clamp(self, value):
        return max(
            self._minimum,
            min(self._maximum, int(value)),
        )

    def _make_button(
        self,
        icon_filename,
        *,
        object_name,
        accessible_name,
        tooltip,
    ):
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setIcon(
            QIcon(str(STATUS_BAR_ICON_DIR / icon_filename))
        )
        button.setIconSize(
            QSize(STATUS_ICON_SIZE, STATUS_ICON_SIZE)
        )
        button.setFixedSize(STATUS_BUTTON_SIZE, STATUS_BUTTON_SIZE)
        button.setStyleSheet(ICON_BUTTON_STYLE)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(accessible_name)
        button.setToolTip(tooltip)
        return button

    def _update_button_states(self):
        self.minus_button.setEnabled(
            self._value < self._maximum
        )
        self.plus_button.setEnabled(
            self._value > self._minimum
        )

    def _update_accessible_value(self):
        self.setAccessibleName(
            f"Poster size: {self._value} posters per row"
        )
