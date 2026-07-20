from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from app.media_board import (
    DEFAULT_POSTERS_PER_ROW,
    MAX_POSTERS_PER_ROW,
    MIN_POSTERS_PER_ROW,
)


class PostersPerRowControl(QWidget):
    """Compact status-bar control for changing the Watchlist density."""

    value_changed = Signal(int)

    def __init__(
        self,
        parent=None,
        *,
        value=DEFAULT_POSTERS_PER_ROW,
    ):
        super().__init__(parent)

        self.setObjectName("postersPerRowControl")
        self.setAccessibleName("Posters per row")
        self._value = self._clamp(value)

        self.title_label = QLabel("Posters per row", self)
        self.title_label.setObjectName("postersPerRowLabel")

        self.decrease_button = self._make_button(
            "\N{MINUS SIGN}",
            object_name="decreasePostersPerRowButton",
            accessible_name="Decrease posters per row",
            tooltip="Show fewer posters per row",
        )
        self.minus_button = self.decrease_button

        self.value_label = QLabel(str(self._value), self)
        self.value_label.setObjectName("postersPerRowValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setMinimumWidth(
            self.value_label.fontMetrics().horizontalAdvance("10")
        )
        self._update_accessible_value()

        self.increase_button = self._make_button(
            "+",
            object_name="increasePostersPerRowButton",
            accessible_name="Increase posters per row",
            tooltip="Show more posters per row",
        )
        self.plus_button = self.increase_button

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.decrease_button)
        layout.addWidget(self.value_label)
        layout.addWidget(self.increase_button)

        self.decrease_button.clicked.connect(self.decrement)
        self.increase_button.clicked.connect(self.increment)
        self._update_button_states()

    def value(self):
        return self._value

    @property
    def posters_per_row(self):
        return self._value

    def set_value(self, value):
        clamped_value = self._clamp(value)

        if clamped_value == self._value:
            self._update_button_states()
            return

        self._value = clamped_value
        self.value_label.setText(str(self._value))
        self._update_accessible_value()
        self._update_button_states()
        self.value_changed.emit(self._value)

    def decrement(self):
        self.set_value(self._value - 1)

    def increment(self):
        self.set_value(self._value + 1)

    @staticmethod
    def _clamp(value):
        return max(
            MIN_POSTERS_PER_ROW,
            min(MAX_POSTERS_PER_ROW, int(value)),
        )

    def _make_button(
        self,
        text,
        *,
        object_name,
        accessible_name,
        tooltip,
    ):
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setText(text)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(accessible_name)
        button.setToolTip(tooltip)
        return button

    def _update_button_states(self):
        self.decrease_button.setEnabled(
            self._value > MIN_POSTERS_PER_ROW
        )
        self.increase_button.setEnabled(
            self._value < MAX_POSTERS_PER_ROW
        )

    def _update_accessible_value(self):
        self.value_label.setAccessibleName(
            f"Current posters per row: {self._value}"
        )
