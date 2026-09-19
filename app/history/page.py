from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QScrollArea, QStyle, QVBoxLayout, QWidget

from .constants import DEFAULT_HISTORY_POSTERS_PER_ROW
from .grid import HistoryGridBoard
from .repository import HISTORY_DEFAULT_FILTER_TEXT, load_default_history_entries
from app.ui.top_bar import TopBar
from db.connection import get_connection


HISTORY_BACKGROUND_COLOR = "#F1F1F1"


class HistoryPage(QWidget):
    status_message_changed = Signal(str)
    density_changed = Signal(int)
    find_media_requested = Signal(str)
    details_requested = Signal(object)
    watch_entry_details_requested = Signal(int, int)

    def __init__(self, parent=None, *, posters_per_row=DEFAULT_HISTORY_POSTERS_PER_ROW):
        super().__init__(parent)
        self._is_loaded = False
        self._is_invalidated = True
        self._status_message = ""
        self.entries = []
        self._pending_anchor = None
        self._pending_resize_anchor = None
        self._last_grid_viewport_width = None
        self._build_ui(posters_per_row)
        self._anchor_restore_timer = QTimer(self)
        self._anchor_restore_timer.setSingleShot(True)
        self._anchor_restore_timer.timeout.connect(self._apply_pending_anchor)
        self._grid_resize_timer = QTimer(self)
        self._grid_resize_timer.setSingleShot(True)
        self._grid_resize_timer.timeout.connect(self._apply_grid_viewport_resize)

    @property
    def status_message(self):
        return self._status_message

    @property
    def is_loaded(self):
        return self._is_loaded

    @property
    def is_invalidated(self):
        return self._is_invalidated

    @property
    def posters_per_row(self):
        return self.grid_board.posters_per_row

    def clear_find_media_query(self):
        self.top_bar.find_media_input.clear()

    @property
    def active_scroll_area(self):
        return self.grid_scroll_area

    def _build_ui(self, posters_per_row):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.top_bar = TopBar(
            filter_label_text="Filter History:",
            default_filter_text=HISTORY_DEFAULT_FILTER_TEXT,
        )
        self.top_bar.filter_submitted.connect(self.on_filter_input)
        self.top_bar.find_media_submitted.connect(
            self.find_media_requested.emit
        )

        self.grid_board = HistoryGridBoard(
            posters_per_row=posters_per_row,
        )
        self.grid_board.setObjectName("historyGridContent")
        self.grid_board.details_requested.connect(
            self.details_requested.emit
        )

        self.grid_scroll_area = QScrollArea(self)
        self.grid_scroll_area.setObjectName("historyGridScrollArea")
        self.grid_scroll_area.setWidgetResizable(True)
        self.grid_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.grid_scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.grid_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_scroll_area.viewport().setObjectName(
            "historyGridScrollViewport"
        )
        self.grid_scroll_area.setStyleSheet(
            f"""
            QScrollArea#historyGridScrollArea,
            QWidget#historyGridScrollViewport,
            QWidget#historyGridContent {{
                background-color: {HISTORY_BACKGROUND_COLOR};
            }}
            """
        )
        self.grid_scroll_area.setWidget(self.grid_board)
        self.grid_scroll_area.viewport().installEventFilter(self)

        self.grid_board.watch_entry_details_requested.connect(
            self.watch_entry_details_requested.emit
        )
        layout.addWidget(self.top_bar)
        layout.addWidget(self.grid_scroll_area, 1)

    def ensure_loaded(self):
        if not self._is_loaded or self._is_invalidated:
            self.refresh_history(
                reset_scroll=False,
                preserve_scroll=self._is_loaded,
            )

        return self.entries

    def invalidate(self):
        self._is_invalidated = True

    def on_filter_input(self, filter_text):
        if filter_text != HISTORY_DEFAULT_FILTER_TEXT:
            print("Filter History:", filter_text)
            return

        self.refresh_history(reset_scroll=True, preserve_scroll=False)

    def refresh_history(self, *, reset_scroll=False, preserve_scroll=True):
        anchor = self._take_navigation_anchor(
            preserve=preserve_scroll and self._is_loaded and not reset_scroll
        )
        with get_connection() as conn:
            self.entries = list(load_default_history_entries(conn))
        self.grid_board.set_entries(self.entries)
        self.grid_board.set_layout_width(self._stable_grid_width())
        self._is_loaded = True
        self._is_invalidated = False
        self._set_status_message(_format_entry_count(len(self.entries)))
        if reset_scroll or anchor is None:
            self._set_all_scroll_values(0)
        else:
            self._restore_anchor_later(anchor)
        return self.entries

    def set_posters_per_row(self, posters_per_row):
        anchor = self._take_navigation_anchor()
        self.grid_board.set_layout_width(self._stable_grid_width())
        changed = self.grid_board.set_posters_per_row(posters_per_row)
        self._restore_anchor_later(anchor)
        if changed:
            self.density_changed.emit(self.posters_per_row)
        return changed

    def eventFilter(self, watched, event):
        scroll = getattr(self, "grid_scroll_area", None)
        if scroll is not None and watched is scroll.viewport() and event.type() == QEvent.Type.Resize:
            width = event.size().width()
            if width != self._last_grid_viewport_width:
                self._pending_resize_anchor = self._pending_anchor or self._capture_scroll_anchor()
                self._last_grid_viewport_width = width
                timer = getattr(self, "_grid_resize_timer", None)
                if timer is not None:
                    timer.start(0)
        return super().eventFilter(watched, event)

    def _apply_grid_viewport_resize(self):
        anchor = self._pending_resize_anchor
        self._pending_resize_anchor = None
        self.grid_board.set_layout_width(self._stable_grid_width())
        self._restore_anchor_later(anchor)

    def _stable_grid_width(self):
        viewport_width = self.grid_scroll_area.viewport().width()
        scroll_bar = self.grid_scroll_area.verticalScrollBar()
        is_transient = bool(
            self.grid_scroll_area.style().styleHint(
                QStyle.StyleHint.SH_ScrollBar_Transient,
                None,
                scroll_bar,
            )
        )

        if (
            is_transient
            or scroll_bar.isVisibleTo(self.grid_scroll_area)
        ):
            return max(1, viewport_width)

        return max(
            1,
            viewport_width - scroll_bar.sizeHint().width(),
        )

    def _active_entry_widgets(self):
        return list(self.grid_board.tiles)

    def _capture_scroll_anchor(self):
        widgets = self._active_entry_widgets()

        if not widgets:
            return None

        scroll_value = (
            self.active_scroll_area.verticalScrollBar().value()
        )

        for index, widget in enumerate(widgets):
            if widget.geometry().bottom() >= scroll_value:
                return (
                    widget.entry.key,
                    index,
                    scroll_value - widget.geometry().top(),
                    tuple(
                        candidate.entry.key
                        for candidate in widgets
                    ),
                )

        last_index = len(widgets) - 1
        last_widget = widgets[last_index]
        return (
            last_widget.entry.key,
            last_index,
            scroll_value - last_widget.geometry().top(),
            tuple(
                candidate.entry.key
                for candidate in widgets
            ),
        )

    def _take_navigation_anchor(self, *, preserve=True):
        anchor = None
        if preserve:
            anchor = self._pending_anchor or self._pending_resize_anchor or self._capture_scroll_anchor()
        self._cancel_pending_navigation()
        return anchor

    def _cancel_pending_navigation(self):
        if self._anchor_restore_timer.isActive():
            self._anchor_restore_timer.stop()

        if self._grid_resize_timer.isActive():
            self._grid_resize_timer.stop()

        self._pending_anchor = None
        self._pending_resize_anchor = None

    def _restore_anchor_later(self, anchor):
        if anchor is not None:
            self._pending_anchor = anchor
            self._anchor_restore_timer.start(0)

    def _apply_pending_anchor(self):
        pending = self._pending_anchor
        self._pending_anchor = None

        if pending is None:
            return

        anchor = pending
        entry_key, previous_index, offset, previous_keys = anchor
        widgets = self._active_entry_widgets()

        if not widgets:
            self.active_scroll_area.verticalScrollBar().setValue(0)
            return

        widgets_by_key = {}

        for widget in widgets:
            widgets_by_key.setdefault(widget.entry.key, widget)

        target_widget = widgets_by_key.get(entry_key)

        if target_widget is None:
            for distance in range(1, len(previous_keys)):
                following_index = previous_index + distance

                if following_index < len(previous_keys):
                    target_widget = widgets_by_key.get(
                        previous_keys[following_index]
                    )

                if target_widget is not None:
                    break

                preceding_index = previous_index - distance

                if preceding_index >= 0:
                    target_widget = widgets_by_key.get(
                        previous_keys[preceding_index]
                    )

                if target_widget is not None:
                    break

        if target_widget is None:
            target_widget = widgets[
                min(previous_index, len(widgets) - 1)
            ]

        offset = min(
            offset,
            max(0, target_widget.height() - 1),
        )
        self._set_active_scroll_value(
            target_widget.geometry().top() + offset
        )

    def _set_active_scroll_value(self, target_value):
        scroll_bar = self.active_scroll_area.verticalScrollBar()
        scroll_bar.setValue(
            max(
                scroll_bar.minimum(),
                min(int(target_value), scroll_bar.maximum()),
            )
        )

    def _set_all_scroll_values(self, value):
        self._cancel_pending_navigation()
        self.grid_scroll_area.verticalScrollBar().setValue(value)

    def _set_status_message(self, message):
        self._status_message = message
        self.status_message_changed.emit(message)


def _format_entry_count(count):
    noun = "entry" if count == 1 else "entries"
    return f"{count} history {noun} – Showing: All Time, Newest First"
