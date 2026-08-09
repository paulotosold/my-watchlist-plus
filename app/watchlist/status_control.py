from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from app.posters_per_row_control import (
    ICON_BUTTON_STYLE,
    PostersPerRowControl,
)
from .board import (
    DEFAULT_POSTERS_PER_ROW,
    MAX_POSTERS_PER_ROW,
    MIN_POSTERS_PER_ROW,
)


ASSETS_DIRECTORY = Path(__file__).resolve().parents[1] / "assets"
STATUS_ICON_SIZE = 20
STATUS_BUTTON_SIZE = 24
STATUS_LEFT_MARGIN = 12
STATUS_RIGHT_MARGIN = 12
FILTERED_LABEL_MAX_TEXT = "9999 filtered titles"
PINNED_BUTTON_MAX_TEXT = "99 pinned"
PINNED_PILL_HEIGHT = 25
PINNED_PILL_RADIUS = PINNED_PILL_HEIGHT // 2
PINNED_CLEAR_BUTTON_SIZE = PINNED_PILL_HEIGHT - 2
PINNED_CLEAR_ICON_SIZE = 18
PINNED_CONTROL_RADIUS = PINNED_CLEAR_BUTTON_SIZE // 2
PINNED_CLEAR_CONTENT_TOP_PADDING = 2
PINNED_PILL_INACTIVE_BACKGROUND = "#ffffff"
PINNED_PILL_ACTIVE_BACKGROUND = "#8fc4ff"
PINNED_PILL_INACTIVE_BORDER = "#929292"
PINNED_PILL_ACTIVE_BORDER = "#4f93cc"
PINNED_PILL_TEXT_COLOR = "#202020"

PINNED_PILL_STYLE = f"""
QFrame#pinnedStatusPill {{
    background: {PINNED_PILL_INACTIVE_BACKGROUND};
    border: 1px solid {PINNED_PILL_INACTIVE_BORDER};
    border-radius: {PINNED_PILL_RADIUS}px;
}}
QFrame#pinnedStatusPill[active="true"] {{
    background: {PINNED_PILL_ACTIVE_BACKGROUND};
    border-color: {PINNED_PILL_ACTIVE_BORDER};
}}
QToolButton#pinnedStatusButton,
QToolButton#clearPinnedButton {{
    background: transparent;
    border: 1px solid transparent;
    color: {PINNED_PILL_TEXT_COLOR};
    padding: 0;
}}
QToolButton#pinnedStatusButton {{
    padding-left: 8px;
    padding-right: 4px;
}}
QToolButton#clearPinnedButton {{
    padding-top: {PINNED_CLEAR_CONTENT_TOP_PADDING}px;
}}
QToolButton#clearPinnedButton:hover {{
    background: rgba(0, 0, 0, 18);
    border-radius: {PINNED_CONTROL_RADIUS}px;
}}
QToolButton#pinnedStatusButton:focus,
QToolButton#clearPinnedButton:focus {{
    border: 1px dotted #3f3f3f;
    border-radius: {PINNED_CONTROL_RADIUS}px;
}}
"""


class WatchlistStatusControl(QWidget):
    """Permanent Watchlist actions and view controls for a status bar."""

    reload_requested = Signal()
    pinned_only_requested = Signal(bool)
    clear_all_pins_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("watchlistStatusControl")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self._filtered_count = 0
        self._pinned_count = 0
        self._pinned_only = False

        self.reload_button = self._make_icon_button(
            "status_bar_reload.png",
            object_name="reloadWatchlistButton",
            accessible_name="Reload watchlist",
            tooltip="Reload the watchlist",
        )

        self.filtered_label = QLabel(self)
        self.filtered_label.setObjectName("filteredStatusLabel")
        self.filtered_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.filtered_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.pinned_pill = QFrame(self)
        self.pinned_pill.setObjectName("pinnedStatusPill")
        self.pinned_pill.setProperty("active", False)
        self.pinned_pill.setFixedHeight(PINNED_PILL_HEIGHT)
        self.pinned_pill.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self.pinned_pill.setStyleSheet(PINNED_PILL_STYLE)

        self.pinned_button = QToolButton(self.pinned_pill)
        self.pinned_button.setObjectName("pinnedStatusButton")
        self.pinned_button.setCheckable(True)
        self.pinned_button.setFixedHeight(
            PINNED_PILL_HEIGHT - 2
        )
        self.pinned_button.setFocusPolicy(
            Qt.FocusPolicy.TabFocus
        )
        self.pinned_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.clear_pins_button = QToolButton(self.pinned_pill)
        self.clear_pins_button.setObjectName("clearPinnedButton")
        self.clear_pins_button.setIcon(
            QIcon(str(ASSETS_DIRECTORY / "status_bar_close.png"))
        )
        self.clear_pins_button.setIconSize(
            QSize(
                PINNED_CLEAR_ICON_SIZE,
                PINNED_CLEAR_ICON_SIZE,
            )
        )
        self.clear_pins_button.setFixedSize(
            PINNED_CLEAR_BUTTON_SIZE,
            PINNED_CLEAR_BUTTON_SIZE,
        )
        self.clear_pins_button.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus
        )
        self.clear_pins_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.clear_pins_button.setAccessibleName(
            "Clear all pinned"
        )
        self.clear_pins_button.setToolTip("Clear all pinned")

        self.pinned_layout = QHBoxLayout(self.pinned_pill)
        self.pinned_layout.setContentsMargins(1, 0, 1, 0)
        self.pinned_layout.setSpacing(0)
        self.pinned_layout.addWidget(self.pinned_button)
        self.pinned_layout.addWidget(self.clear_pins_button)

        self.poster_size_control = PostersPerRowControl(
            self,
            value=DEFAULT_POSTERS_PER_ROW,
            minimum=MIN_POSTERS_PER_ROW,
            maximum=MAX_POSTERS_PER_ROW,
        )

        # macOS gives tool buttons a smaller class font. Reapplying the
        # label's size marks it as explicit while retaining system styling.
        status_text_font = self.poster_size_control.title_label.font()
        if status_text_font.pixelSize() > 0:
            status_text_font.setPixelSize(
                status_text_font.pixelSize()
            )
        else:
            status_text_font.setPointSizeF(
                status_text_font.pointSizeF()
            )

        self.filtered_label.setFont(status_text_font)
        self.pinned_button.setFont(status_text_font)
        self.clear_pins_button.setFont(status_text_font)

        filtered_metrics = self.filtered_label.fontMetrics()
        self.filtered_label_width = (
            filtered_metrics.horizontalAdvance(
                FILTERED_LABEL_MAX_TEXT
            )
        )
        self.filtered_label.setFixedWidth(
            self.filtered_label_width
        )
        self.pinned_button.setText(PINNED_BUTTON_MAX_TEXT)
        self.pinned_button_width = (
            self.pinned_button.sizeHint().width()
        )
        self.pinned_button.setFixedWidth(
            self.pinned_button_width
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            STATUS_LEFT_MARGIN,
            0,
            STATUS_RIGHT_MARGIN,
            0,
        )
        layout.setSpacing(8)
        layout.addWidget(self.reload_button)
        layout.addWidget(self.filtered_label)
        layout.addWidget(
            self.pinned_pill,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addStretch(1)
        layout.addWidget(self.poster_size_control)

        self.reload_button.clicked.connect(
            self.reload_requested.emit
        )
        self.pinned_button.clicked.connect(
            self._request_pinned_only
        )
        self.clear_pins_button.clicked.connect(
            self.clear_all_pins_requested.emit
        )

        self.setTabOrder(
            self.reload_button,
            self.pinned_button,
        )
        self.setTabOrder(
            self.pinned_button,
            self.clear_pins_button,
        )
        self.setTabOrder(
            self.clear_pins_button,
            self.poster_size_control.minus_button,
        )

        self.set_state(
            filtered_count=0,
            pinned_count=0,
            pinned_only=False,
        )

    @property
    def filtered_count(self):
        return self._filtered_count

    @property
    def pinned_count(self):
        return self._pinned_count

    @property
    def pinned_only(self):
        return self._pinned_only

    def set_state(
        self,
        filtered_count,
        pinned_count,
        pinned_only,
    ):
        """Synchronize visual state without emitting request signals."""
        self._filtered_count = max(0, int(filtered_count))
        self._pinned_count = max(0, int(pinned_count))
        self._pinned_only = (
            bool(pinned_only) and self._pinned_count > 0
        )

        filtered_noun = (
            "title" if self._filtered_count == 1 else "titles"
        )
        filtered_text = (
            f"{self._filtered_count} filtered {filtered_noun}"
        )
        pinned_text = f"{self._pinned_count} pinned"

        self.filtered_label.setText(filtered_text)
        self.pinned_button.setText(pinned_text)
        self.filtered_label.setAccessibleName(filtered_text)

        self.pinned_button.setChecked(self._pinned_only)
        has_pins = self._pinned_count > 0
        self.pinned_button.setEnabled(has_pins)
        self.clear_pins_button.setEnabled(has_pins)
        self.pinned_pill.setVisible(has_pins)
        self._update_pinned_pill()

    def _request_pinned_only(self, pinned_only):
        self._pinned_only = (
            bool(pinned_only) and self._pinned_count > 0
        )
        self.pinned_button.setChecked(self._pinned_only)
        self._update_pinned_pill()
        self.pinned_only_requested.emit(self._pinned_only)

    def _update_pinned_pill(self):
        self.pinned_layout.invalidate()
        self.pinned_pill.setFixedWidth(
            self.pinned_layout.sizeHint().width()
        )
        self.pinned_pill.setProperty(
            "active",
            self._pinned_only,
        )
        style = self.pinned_pill.style()
        style.unpolish(self.pinned_pill)
        style.polish(self.pinned_pill)
        self.pinned_pill.update()

        action_text = (
            "Show all filtered media"
            if self._pinned_only
            else "Show pinned media only"
        )
        self.pinned_button.setAccessibleName(action_text)
        self.pinned_button.setToolTip(action_text)

    def _make_icon_button(
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
            QIcon(str(ASSETS_DIRECTORY / icon_filename))
        )
        button.setIconSize(
            QSize(STATUS_ICON_SIZE, STATUS_ICON_SIZE)
        )
        button.setFixedSize(STATUS_BUTTON_SIZE, STATUS_BUTTON_SIZE)
        button.setStyleSheet(ICON_BUTTON_STYLE)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(accessible_name)
        button.setToolTip(tooltip)
        return button
