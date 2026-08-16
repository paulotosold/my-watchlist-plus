"""Status-bar controls for the Cabinet page."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.ui.posters_per_row_control import PostersPerRowControl

from .board import (
    DEFAULT_POSTERS_PER_ROW,
    MAX_POSTERS_PER_ROW,
    MIN_POSTERS_PER_ROW,
)


class CabinetStatusControl(QWidget):
    posters_per_row_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cabinetStatusControl")
        self.setAccessibleName("Cabinet status controls")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._title_count = 0
        self._posters_per_row = DEFAULT_POSTERS_PER_ROW

        self.count_label = QLabel(self)
        self.count_label.setObjectName("cabinetCountLabel")
        self.count_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.poster_size_control = PostersPerRowControl(
            self,
            value=DEFAULT_POSTERS_PER_ROW,
            minimum=MIN_POSTERS_PER_ROW,
            maximum=MAX_POSTERS_PER_ROW,
        )
        self.count_label.setFont(self.poster_size_control.title_label.font())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)
        layout.addWidget(self.count_label)
        layout.addStretch(1)
        layout.addWidget(self.poster_size_control)

        self.poster_size_control.value_changed.connect(
            self._request_posters_per_row
        )
        self.set_state(0, DEFAULT_POSTERS_PER_ROW)

    @property
    def title_count(self):
        return self._title_count

    @property
    def posters_per_row(self):
        return self._posters_per_row

    def set_state(self, title_count, posters_per_row):
        self._title_count = max(0, int(title_count))
        noun = "title" if self._title_count == 1 else "titles"
        text = (
            f"{self._title_count} {noun} -- "
            "Showing: Cabinet Worthy, Custom Order"
        )
        self.count_label.setText(text)
        self.count_label.setAccessibleName(text)
        blocker = QSignalBlocker(self.poster_size_control)
        self.poster_size_control.set_value(posters_per_row)
        self._posters_per_row = self.poster_size_control.posters_per_row
        del blocker

    def _request_posters_per_row(self, posters_per_row):
        self._posters_per_row = posters_per_row
        self.posters_per_row_requested.emit(posters_per_row)
