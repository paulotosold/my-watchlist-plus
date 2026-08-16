from __future__ import annotations

from PySide6.QtCore import QSize, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from app.ui.posters_per_row_control import PostersPerRowControl
from .constants import (
    ASSETS_DIRECTORY,
    DEFAULT_HISTORY_POSTERS_PER_ROW,
    HISTORY_VIEW_GRID,
    HISTORY_VIEW_LIST,
    MAX_HISTORY_POSTERS_PER_ROW,
    MIN_HISTORY_POSTERS_PER_ROW,
)


STATUS_ICON_SIZE = 20
STATUS_BUTTON_SIZE = 24
STATUS_LEFT_MARGIN = 12
STATUS_RIGHT_MARGIN = 12

ACTIVE_VIEW_BACKGROUND = "#8fc4ff"
ACTIVE_VIEW_BORDER = "#4f93cc"
VIEW_BUTTON_HOVER_BACKGROUND = "rgba(0, 0, 0, 18)"
VIEW_BUTTON_RADIUS = 5

VIEW_BUTTON_STYLE = f"""
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {VIEW_BUTTON_RADIUS}px;
    padding: 0;
}}
QToolButton:focus {{
    border: 1px dotted #3f3f3f;
}}
QToolButton:hover {{
    background: {VIEW_BUTTON_HOVER_BACKGROUND};
}}
QToolButton:checked {{
    background: {ACTIVE_VIEW_BACKGROUND};
    border: 1px solid {ACTIVE_VIEW_BORDER};
}}
"""


class HistoryStatusControl(QWidget):
    """History count, density, and view controls for a status bar."""

    view_mode_requested = Signal(str)
    posters_per_row_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("historyStatusControl")
        self.setAccessibleName("History status controls")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self._watched_count = 0
        self._view_mode = HISTORY_VIEW_GRID
        self._posters_per_row = DEFAULT_HISTORY_POSTERS_PER_ROW

        self.count_label = QLabel(self)
        self.count_label.setObjectName("historyCountLabel")
        self.count_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.count_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.watched_count_label = self.count_label

        self.poster_size_control = PostersPerRowControl(
            self,
            value=DEFAULT_HISTORY_POSTERS_PER_ROW,
            minimum=MIN_HISTORY_POSTERS_PER_ROW,
            maximum=MAX_HISTORY_POSTERS_PER_ROW,
        )

        self.view_label = QLabel("View", self)
        self.view_label.setObjectName("historyViewLabel")
        self.view_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.view_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.grid_view_button = self._make_view_button(
            "status_bar_view_grid.png",
            object_name="historyGridViewButton",
            accessible_name="Grid view",
            tooltip="Show history as a grid",
        )
        self.list_view_button = self._make_view_button(
            "status_bar_view_list.png",
            object_name="historyListViewButton",
            accessible_name="List view",
            tooltip="Show history as a list",
        )
        self.list_button = self.list_view_button
        self.grid_button = self.grid_view_button

        self.view_button_group = QButtonGroup(self)
        self.view_button_group.setExclusive(True)
        self.view_button_group.addButton(self.grid_view_button)
        self.view_button_group.addButton(self.list_view_button)

        # Keep status-bar text at one system size on platforms that give
        # tool-button-adjacent controls a smaller implicit font.
        status_text_font = self.poster_size_control.title_label.font()
        self.count_label.setFont(status_text_font)
        self.view_label.setFont(status_text_font)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            STATUS_LEFT_MARGIN,
            0,
            STATUS_RIGHT_MARGIN,
            0,
        )
        layout.setSpacing(8)
        layout.addWidget(self.count_label)
        layout.addStretch(1)
        layout.addWidget(self.poster_size_control)
        layout.addWidget(self.view_label)
        layout.addWidget(self.grid_view_button)
        layout.addWidget(self.list_view_button)

        self.grid_view_button.clicked.connect(
            lambda _checked=False: self._request_view_mode(
                HISTORY_VIEW_GRID
            )
        )
        self.list_view_button.clicked.connect(
            lambda _checked=False: self._request_view_mode(
                HISTORY_VIEW_LIST
            )
        )
        self.poster_size_control.value_changed.connect(
            self._request_posters_per_row
        )

        self.setTabOrder(
            self.poster_size_control.minus_button,
            self.poster_size_control.plus_button,
        )
        self.setTabOrder(
            self.poster_size_control.plus_button,
            self.grid_view_button,
        )
        self.setTabOrder(
            self.grid_view_button,
            self.list_view_button,
        )

        self.set_state(
            watched_count=0,
            view_mode=HISTORY_VIEW_GRID,
            posters_per_row=DEFAULT_HISTORY_POSTERS_PER_ROW,
        )

    @property
    def watched_count(self):
        return self._watched_count

    @property
    def view_mode(self):
        return self._view_mode

    @property
    def posters_per_row(self):
        return self._posters_per_row

    def set_state(
        self,
        watched_count,
        view_mode,
        posters_per_row,
    ):
        """Synchronize visual state without emitting request signals."""
        normalized_mode = self._normalize_view_mode(view_mode)
        self._watched_count = max(0, int(watched_count))
        self._view_mode = normalized_mode

        count_noun = (
            "entry" if self._watched_count == 1 else "entries"
        )
        count_text = (
            f"{self._watched_count} history {count_noun} – "
            "Showing: All Time, Newest First"
        )
        self.count_label.setText(count_text)
        self.count_label.setAccessibleName(count_text)

        blocker = QSignalBlocker(self.poster_size_control)
        self.poster_size_control.set_value(posters_per_row)
        self._posters_per_row = (
            self.poster_size_control.posters_per_row
        )
        del blocker

        self._sync_view_buttons()
        self._update_density_visibility()

    def set_watched_count(self, watched_count):
        self.set_state(
            watched_count,
            self._view_mode,
            self._posters_per_row,
        )

    def set_view_mode(self, view_mode):
        self.set_state(
            self._watched_count,
            view_mode,
            self._posters_per_row,
        )

    def set_posters_per_row(self, posters_per_row):
        self.set_state(
            self._watched_count,
            self._view_mode,
            posters_per_row,
        )

    def _request_view_mode(self, view_mode):
        normalized_mode = self._normalize_view_mode(view_mode)

        if normalized_mode == self._view_mode:
            self._sync_view_buttons()
            return

        self._view_mode = normalized_mode
        self._sync_view_buttons()
        self._update_density_visibility()
        self.view_mode_requested.emit(self._view_mode)

    def _request_posters_per_row(self, posters_per_row):
        self._posters_per_row = int(posters_per_row)
        self.posters_per_row_requested.emit(self._posters_per_row)

    def _sync_view_buttons(self):
        self.list_view_button.setChecked(
            self._view_mode == HISTORY_VIEW_LIST
        )
        self.grid_view_button.setChecked(
            self._view_mode == HISTORY_VIEW_GRID
        )

    def _update_density_visibility(self):
        self.poster_size_control.setVisible(
            self._view_mode == HISTORY_VIEW_GRID
        )

    def _make_view_button(
        self,
        icon_filename,
        *,
        object_name,
        accessible_name,
        tooltip,
    ):
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setCheckable(True)
        button.setIcon(
            QIcon(str(ASSETS_DIRECTORY / icon_filename))
        )
        button.setIconSize(
            QSize(STATUS_ICON_SIZE, STATUS_ICON_SIZE)
        )
        button.setFixedSize(STATUS_BUTTON_SIZE, STATUS_BUTTON_SIZE)
        button.setStyleSheet(VIEW_BUTTON_STYLE)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(accessible_name)
        button.setToolTip(tooltip)
        return button

    @staticmethod
    def _normalize_view_mode(view_mode):
        normalized_mode = str(view_mode).strip().lower()

        if normalized_mode not in (
            HISTORY_VIEW_LIST,
            HISTORY_VIEW_GRID,
        ):
            raise ValueError(
                f"Unsupported history view mode: {view_mode!r}"
            )

        return normalized_mode
