from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.ui.posters_per_row_control import PostersPerRowControl
from .constants import (
    DEFAULT_HISTORY_POSTERS_PER_ROW,
    HISTORY_POSTERS_PER_ROW_OPTIONS,
)
from .page import _format_entry_count


class HistoryStatusControl(QWidget):
    """Entry count and poster density for the History grid."""

    posters_per_row_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historyStatusControl")
        self.setAccessibleName("History status controls")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._watched_count = 0
        self._posters_per_row = DEFAULT_HISTORY_POSTERS_PER_ROW
        self.count_label = QLabel(self)
        self.count_label.setObjectName("historyCountLabel")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.watched_count_label = self.count_label
        self.poster_size_control = PostersPerRowControl(
            self,
            value=DEFAULT_HISTORY_POSTERS_PER_ROW,
            options=HISTORY_POSTERS_PER_ROW_OPTIONS,
        )
        self.count_label.setFont(self.poster_size_control.title_label.font())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)
        layout.addWidget(self.count_label)
        layout.addStretch(1)
        layout.addWidget(self.poster_size_control)
        self.poster_size_control.value_changed.connect(self._request_posters_per_row)
        self.set_state(0, DEFAULT_HISTORY_POSTERS_PER_ROW)

    @property
    def watched_count(self):
        return self._watched_count

    @property
    def posters_per_row(self):
        return self._posters_per_row

    def set_state(self, watched_count, posters_per_row):
        self._watched_count = max(0, int(watched_count))
        text = _format_entry_count(self._watched_count)
        self.count_label.setText(text)
        self.count_label.setAccessibleName(text)
        blocker = QSignalBlocker(self.poster_size_control)
        self.poster_size_control.set_value(posters_per_row)
        self._posters_per_row = self.poster_size_control.posters_per_row
        del blocker

    def set_watched_count(self, watched_count):
        self.set_state(watched_count, self._posters_per_row)

    def set_posters_per_row(self, posters_per_row):
        self.set_state(self._watched_count, posters_per_row)

    def _request_posters_per_row(self, posters_per_row):
        self._posters_per_row = posters_per_row
        self.posters_per_row_requested.emit(posters_per_row)
