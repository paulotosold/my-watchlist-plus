from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    DEFAULT_HISTORY_POSTERS_PER_ROW,
    HISTORY_VIEW_GRID,
    HISTORY_VIEW_LIST,
    HISTORY_VIEW_MODES,
)
from .entry_widget import HistoryEntryWidget
from .grid import HistoryGridBoard
from .repository import (
    HISTORY_DEFAULT_FILTER_TEXT,
    load_default_history_entries,
)
from app.media_repository import (
    ConcurrentEditError,
    apply_media_state_patch,
    get_media_state,
)
from app.ui.top_bar import TopBar
from db.connection import get_connection


HISTORY_BACKGROUND_COLOR = "#F1F1F1"


class HistoryPage(QWidget):
    status_message_changed = Signal(str)
    view_state_changed = Signal(str, int)
    find_media_requested = Signal(str)
    details_requested = Signal(object)
    library_changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        posters_per_row=DEFAULT_HISTORY_POSTERS_PER_ROW,
    ):
        super().__init__(parent)

        self._is_loaded = False
        self._is_invalidated = True
        self._status_message = ""
        self._view_mode = HISTORY_VIEW_GRID
        self.entries = []
        self.entry_widgets = []
        self._widgets_by_media_id = defaultdict(list)
        self._confirmed_states = {}
        self._list_initialized = False
        self._grid_initialized = False
        self._pending_anchor = None
        self._pending_resize_anchor = None
        self._last_grid_viewport_width = None

        self._build_ui(posters_per_row)

        self._anchor_restore_timer = QTimer(self)
        self._anchor_restore_timer.setSingleShot(True)
        self._anchor_restore_timer.timeout.connect(
            self._apply_pending_anchor
        )

        self._grid_resize_timer = QTimer(self)
        self._grid_resize_timer.setSingleShot(True)
        self._grid_resize_timer.timeout.connect(
            self._apply_grid_viewport_resize
        )

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
    def view_mode(self):
        return self._view_mode

    @property
    def posters_per_row(self):
        return self.grid_board.posters_per_row

    @property
    def active_scroll_area(self):
        if self._view_mode == HISTORY_VIEW_GRID:
            return self.grid_scroll_area

        return self.scroll_area

    def clear_find_media_query(self):
        self.top_bar.find_media_input.clear()

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

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("historyScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.viewport().setObjectName("historyScrollViewport")
        self.scroll_area.setStyleSheet(
            f"""
            QScrollArea#historyScrollArea,
            QWidget#historyScrollViewport,
            QWidget#historyScrollContent {{
                background-color: {HISTORY_BACKGROUND_COLOR};
            }}
            """
        )

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("historyScrollContent")
        self.entries_layout = QVBoxLayout(self.scroll_content)
        self.entries_layout.setContentsMargins(0, 0, 12, 0)
        self.entries_layout.setSpacing(0)
        self.entries_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

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

        self.view_stack = QStackedWidget(self)
        self.view_stack.setObjectName("historyViewStack")
        self.view_stack.addWidget(self.scroll_area)
        self.view_stack.addWidget(self.grid_scroll_area)
        self.view_stack.setCurrentWidget(self.grid_scroll_area)

        layout.addWidget(self.top_bar)
        layout.addWidget(self.view_stack, 1)

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
            preserve=(
                preserve_scroll
                and self._is_loaded
                and not reset_scroll
            )
        )

        with get_connection() as conn:
            entries = load_default_history_entries(conn)

        self.entries = list(entries)

        if self._list_initialized:
            self._render_entries()
        elif self._view_mode == HISTORY_VIEW_LIST:
            self._ensure_list_initialized()

        if (
            self._view_mode == HISTORY_VIEW_GRID
            and not self._grid_initialized
        ):
            self._ensure_grid_initialized()
        elif self._grid_initialized:
            self.grid_board.set_entries(self.entries)
            self.grid_board.set_layout_width(
                self._stable_grid_width()
            )

        self._is_loaded = True
        self._is_invalidated = False
        self._set_status_message(_format_entry_count(len(self.entries)))

        if reset_scroll or anchor is None:
            self._set_all_scroll_values(0)
        else:
            self._restore_anchor_later(anchor)

        return self.entries

    def set_view_mode(self, view_mode):
        view_mode = str(view_mode).strip().lower()

        if view_mode not in HISTORY_VIEW_MODES:
            raise ValueError(f"Unsupported History view mode: {view_mode}")

        if view_mode == self._view_mode:
            return False

        anchor = self._take_navigation_anchor()

        if view_mode == HISTORY_VIEW_GRID:
            self._ensure_grid_initialized()
            self.grid_board.set_layout_width(self._stable_grid_width())
            target_widget = self.grid_scroll_area
        else:
            self._ensure_list_initialized()
            target_widget = self.scroll_area

        self._view_mode = view_mode
        self._restore_anchor_later(anchor)
        self.view_stack.setCurrentWidget(target_widget)
        self.view_state_changed.emit(
            self._view_mode,
            self.posters_per_row,
        )
        return True

    def set_posters_per_row(self, posters_per_row):
        anchor = self._take_navigation_anchor(
            preserve=self._view_mode == HISTORY_VIEW_GRID
        )

        if self._view_mode == HISTORY_VIEW_GRID:
            self.grid_board.set_layout_width(
                self._stable_grid_width()
            )

        changed = self.grid_board.set_posters_per_row(
            posters_per_row
        )

        if not changed:
            if self._view_mode == HISTORY_VIEW_GRID:
                self._restore_anchor_later(anchor)
            return False

        if self._view_mode == HISTORY_VIEW_GRID:
            self._restore_anchor_later(anchor)

        self.view_state_changed.emit(
            self._view_mode,
            self.posters_per_row,
        )
        return True

    def eventFilter(self, watched, event):
        grid_scroll_area = getattr(self, "grid_scroll_area", None)

        if (
            grid_scroll_area is not None
            and watched is grid_scroll_area.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            viewport_width = event.size().width()

            if viewport_width != self._last_grid_viewport_width:
                pending_anchor = (
                    self._pending_anchor[1]
                    if (
                        self._pending_anchor is not None
                        and self._pending_anchor[0]
                        == HISTORY_VIEW_GRID
                    )
                    else None
                )
                self._pending_resize_anchor = pending_anchor or (
                    self._capture_scroll_anchor()
                    if self._view_mode == HISTORY_VIEW_GRID
                    else None
                )
                self._last_grid_viewport_width = viewport_width
                grid_resize_timer = getattr(
                    self,
                    "_grid_resize_timer",
                    None,
                )

                if grid_resize_timer is not None:
                    grid_resize_timer.start(0)

        return super().eventFilter(watched, event)

    def _ensure_grid_initialized(self):
        if self._grid_initialized:
            return

        self.grid_board.set_entries(self.entries)
        self.grid_board.set_layout_width(self._stable_grid_width())
        self._grid_initialized = True

    def _ensure_list_initialized(self):
        if self._list_initialized:
            return

        self._render_entries()
        self._list_initialized = True

    def _apply_grid_viewport_resize(self):
        anchor = self._pending_resize_anchor
        self._pending_resize_anchor = None
        self.grid_board.set_layout_width(self._stable_grid_width())

        if self._view_mode == HISTORY_VIEW_GRID:
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
        if self._view_mode == HISTORY_VIEW_GRID:
            return list(self.grid_board.tiles)

        return list(self.entry_widgets)

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
            if (
                self._pending_anchor is not None
                and self._pending_anchor[0] == self._view_mode
            ):
                anchor = self._pending_anchor[1]
            elif (
                self._view_mode == HISTORY_VIEW_GRID
                and self._pending_resize_anchor is not None
            ):
                anchor = self._pending_resize_anchor
            else:
                anchor = self._capture_scroll_anchor()

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
        if anchor is None:
            return

        self._pending_anchor = (
            self._view_mode,
            anchor,
        )
        self._anchor_restore_timer.start(0)

    def _apply_pending_anchor(self):
        pending = self._pending_anchor
        self._pending_anchor = None

        if pending is None:
            return

        view_mode, anchor = pending

        if view_mode != self._view_mode:
            return

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

        def apply_value():
            for scroll_area in (
                self.scroll_area,
                self.grid_scroll_area,
            ):
                scroll_area.verticalScrollBar().setValue(value)

        apply_value()
        QTimer.singleShot(0, apply_value)

    def _render_entries(self):
        self._clear_entries()
        self._widgets_by_media_id = defaultdict(list)
        self._confirmed_states = {}

        for entry in self.entries:
            widget = HistoryEntryWidget(entry, self.scroll_content)
            widget.details_requested.connect(self.details_requested.emit)
            widget.state_change_requested.connect(
                self._save_inline_state_change
            )
            self.entries_layout.addWidget(widget)
            self.entry_widgets.append(widget)
            self._widgets_by_media_id[entry.state_media_id].append(widget)
            self._confirmed_states[entry.state_media_id] = {
                "watch_state": entry.watch_state,
                "impression": entry.impression,
                "is_cabinet_worthy": entry.is_cabinet_worthy,
            }

        self.entries_layout.addStretch(1)
        self.entries_layout.invalidate()
        self.entries_layout.activate()
        self.scroll_content.updateGeometry()

    def _clear_entries(self):
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self.entry_widgets = []

    def _save_inline_state_change(
        self,
        media_id,
        field,
        expected_value,
        desired_value,
    ):
        confirmed_state = self._confirmed_states.get(media_id)

        if confirmed_state is None:
            return

        if desired_value == confirmed_state.get(field):
            self._sync_media_widgets(media_id, confirmed_state)
            return

        if expected_value != confirmed_state.get(field):
            self._sync_media_widgets(media_id, confirmed_state)
            return

        self._set_media_editing_enabled(media_id, False)

        try:
            with get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                canonical_state = apply_media_state_patch(
                    conn,
                    media_id,
                    expected_values={field: expected_value},
                    changes={field: desired_value},
                )
        except ConcurrentEditError:
            canonical_state = self._reload_media_state(
                media_id,
            )

            if canonical_state is None:
                canonical_state = confirmed_state
            else:
                self.library_changed.emit()

            self._sync_media_widgets(media_id, canonical_state)
            QMessageBox.warning(
                self,
                "History update conflict",
                (
                    "This media changed elsewhere. "
                    "The latest saved values have been loaded."
                ),
            )
        except Exception as exc:
            self._sync_media_widgets(media_id, confirmed_state)
            QMessageBox.warning(
                self,
                "History update failed",
                str(exc),
            )
        else:
            self._sync_media_widgets(media_id, canonical_state)
            self.library_changed.emit()
        finally:
            self._set_media_editing_enabled(media_id, True)

    def _reload_media_state(self, media_id):
        try:
            with get_connection() as conn:
                return get_media_state(conn, media_id)
        except Exception:
            return None

    def _sync_media_widgets(self, media_id, state):
        normalized_state = {
            "watch_state": state.get("watch_state"),
            "impression": state.get("impression"),
            "is_cabinet_worthy": state.get("is_cabinet_worthy"),
        }
        self._confirmed_states[media_id] = normalized_state
        self.entries = [
            replace(
                entry,
                watch_state=normalized_state["watch_state"],
                impression=normalized_state["impression"],
                is_cabinet_worthy=normalized_state[
                    "is_cabinet_worthy"
                ],
            )
            if entry.state_media_id == media_id
            else entry
            for entry in self.entries
        ]
        entries_by_key = {
            entry.key: entry
            for entry in self.entries
            if entry.state_media_id == media_id
        }

        for widget in self._widgets_by_media_id.get(media_id, ()):
            widget.entry = entries_by_key.get(widget.entry.key, widget.entry)
            widget.set_state_values(
                normalized_state["watch_state"],
                normalized_state["impression"],
                normalized_state["is_cabinet_worthy"],
                confirmed=True,
            )

    def _set_media_editing_enabled(self, media_id, enabled):
        for widget in self._widgets_by_media_id.get(media_id, ()):
            widget.set_editing_enabled(enabled)

    def _set_status_message(self, message):
        self._status_message = message
        self.status_message_changed.emit(message)


def _format_entry_count(count):
    noun = "entry" if count == 1 else "entries"
    return f"{count} history {noun} – Showing: All Time, Newest First"
