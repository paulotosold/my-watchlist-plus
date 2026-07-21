from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMenu,
    QSizeGrip,
    QSizePolicy,
    QStatusBar,
    QToolButton,
    QWidget,
)

from app.posters_per_row_control import (
    ICON_BUTTON_STYLE,
    PostersPerRowControl,
)


ASSETS_DIRECTORY = Path(__file__).resolve().parent / "assets"
STATUS_ICON_SIZE = 20
STATUS_BUTTON_SIZE = 24
SEGMENT_BUTTON_HEIGHT = 24
SEGMENT_HORIZONTAL_PADDING = 12
STATUS_LEFT_MARGIN = 12
STATUS_RIGHT_MARGIN = 12

SEGMENT_STYLE = """
QToolButton {
    background: #e8e8e8;
    border: 1px solid #c8c8c8;
    padding: 2px 8px;
}
QToolButton#filteredStatusSegment {
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
}
QToolButton#pinnedStatusSegment {
    border-left: 0;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}
QToolButton:checked {
    background: white;
}
QToolButton:hover:!checked {
    background: #f0f0f0;
}
QToolButton:disabled {
    background: #dedede;
    border-color: #c8c8c8;
    color: #8a8a8a;
}
"""


class ContextMenuToolButton(QToolButton):
    """Tool button that exposes its context menu to mouse and keyboard."""

    context_menu_requested = Signal(QPoint)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(event.pos())
        event.accept()

    def keyPressEvent(self, event):
        is_menu_key = event.key() == Qt.Key.Key_Menu
        is_shift_f10 = (
            event.key() == Qt.Key.Key_F10
            and bool(
                event.modifiers()
                & Qt.KeyboardModifier.ShiftModifier
            )
        )

        if is_menu_key or is_shift_f10:
            self.context_menu_requested.emit(
                self.rect().bottomLeft()
            )
            event.accept()
            return

        super().keyPressEvent(event)


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

        self.filtered_button = self._make_segment_button(
            object_name="filteredStatusSegment",
            accessible_name="Show all filtered media",
            tooltip="Show all filtered media",
        )
        self.pinned_button = self._make_segment_button(
            object_name="pinnedStatusSegment",
            accessible_name="Show pinned media only",
            tooltip="Show pinned media only",
            context_menu=True,
        )

        filtered_metrics = self.filtered_button.fontMetrics()
        pinned_metrics = self.pinned_button.fontMetrics()
        self.filtered_segment_width = (
            filtered_metrics.horizontalAdvance(
                "9999 filtered titles"
            )
            + 2 * SEGMENT_HORIZONTAL_PADDING
        )
        self.pinned_segment_width = (
            pinned_metrics.horizontalAdvance("9999 pinned")
            + 2 * SEGMENT_HORIZONTAL_PADDING
        )
        self.filtered_button.setFixedSize(
            self.filtered_segment_width,
            SEGMENT_BUTTON_HEIGHT,
        )
        self.pinned_button.setFixedSize(
            self.pinned_segment_width,
            SEGMENT_BUTTON_HEIGHT,
        )

        self.segment_group = QButtonGroup(self)
        self.segment_group.setExclusive(True)
        self.segment_group.addButton(self.filtered_button)
        self.segment_group.addButton(self.pinned_button)

        self.segment_container = QWidget(self)
        self.segment_container.setObjectName("watchlistStatusSegments")
        segment_layout = QHBoxLayout(self.segment_container)
        segment_layout.setContentsMargins(0, 0, 0, 0)
        segment_layout.setSpacing(0)
        segment_layout.addWidget(self.filtered_button)
        segment_layout.addWidget(self.pinned_button)

        self.pinned_context_menu = QMenu(self)
        self.clear_all_pins_action = QAction(
            "Clear all pinned",
            self.pinned_context_menu,
        )
        self.pinned_context_menu.addAction(
            self.clear_all_pins_action
        )
        self.poster_size_control = PostersPerRowControl(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            STATUS_LEFT_MARGIN,
            0,
            STATUS_RIGHT_MARGIN,
            0,
        )
        layout.setSpacing(8)
        layout.addWidget(self.reload_button)
        layout.addWidget(self.segment_container)
        layout.addStretch(1)
        layout.addWidget(self.poster_size_control)

        self.reload_button.clicked.connect(
            self.reload_requested.emit
        )
        self.filtered_button.clicked.connect(
            lambda _checked=False: self._request_pinned_only(False)
        )
        self.pinned_button.clicked.connect(
            lambda _checked=False: self._request_pinned_only(True)
        )
        self.pinned_button.context_menu_requested.connect(
            self._show_pinned_context_menu
        )
        self.clear_all_pins_action.triggered.connect(
            self.clear_all_pins_requested.emit
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

        self.filtered_button.setText(filtered_text)
        self.pinned_button.setText(pinned_text)
        self.filtered_button.setAccessibleName(
            f"{filtered_text}, show all"
        )
        self.pinned_button.setAccessibleName(
            f"{pinned_text}, show pinned only"
        )

        self.filtered_button.setChecked(not self._pinned_only)
        self.pinned_button.setChecked(self._pinned_only)
        self.pinned_button.setEnabled(self._pinned_count > 0)
        self.clear_all_pins_action.setEnabled(
            self._pinned_count > 0
        )

    def _request_pinned_only(self, pinned_only):
        self._pinned_only = (
            bool(pinned_only) and self._pinned_count > 0
        )
        self.pinned_only_requested.emit(self._pinned_only)

    def _show_pinned_context_menu(self, position: QPoint):
        self.pinned_context_menu.popup(
            self.pinned_button.mapToGlobal(position)
        )

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
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(accessible_name)
        button.setToolTip(tooltip)
        return button

    def _make_segment_button(
        self,
        *,
        object_name,
        accessible_name,
        tooltip,
        context_menu=False,
    ):
        button_class = (
            ContextMenuToolButton if context_menu else QToolButton
        )
        button = button_class(self)
        button.setObjectName(object_name)
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(accessible_name)
        button.setToolTip(tooltip)
        button.setStyleSheet(SEGMENT_STYLE)
        return button


class WatchlistStatusBar(QStatusBar):
    """Status bar whose Watchlist controls fill its full height."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.watchlist_control = WatchlistStatusControl(self)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(
            self._layout_watchlist_control
        )
        self.setFixedHeight(STATUS_BUTTON_SIZE)
        self._layout_watchlist_control()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_watchlist_control()
        self._layout_timer.start(0)

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_watchlist_control()
        self._layout_timer.start(0)

    def _layout_watchlist_control(self):
        available_width = self.width()
        size_grip = self.findChild(QSizeGrip)

        if size_grip is not None and size_grip.isVisible():
            grip_width = size_grip.width()

            if not 0 < grip_width < self.width():
                grip_width = max(0, size_grip.sizeHint().width())

            available_width = self.width() - grip_width

        if available_width <= 0 and self.width() > 0:
            available_width = self.width()

        self.watchlist_control.setGeometry(
            0,
            0,
            max(0, available_width),
            self.height(),
        )
        self.watchlist_control.raise_()

        if size_grip is not None:
            size_grip.raise_()
