from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.history_entry_widget import HistoryEntryWidget
from app.history_repository import (
    HISTORY_DEFAULT_FILTER_TEXT,
    load_default_history_entries,
)
from app.media_repository import (
    ConcurrentEditError,
    apply_media_state_patch,
    get_media_state,
)
from app.top_bar import TopBar
from db.connection import get_connection


HISTORY_BACKGROUND_COLOR = "#F1F1F1"


class HistoryPage(QWidget):
    status_message_changed = Signal(str)
    find_media_requested = Signal(str)
    details_requested = Signal(object)
    library_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_loaded = False
        self._is_invalidated = True
        self._status_message = ""
        self.entries = []
        self.entry_widgets = []
        self._widgets_by_media_id = defaultdict(list)
        self._confirmed_states = {}
        self._scroll_restore_callback = None

        self._build_ui()

    @property
    def status_message(self):
        return self._status_message

    @property
    def is_loaded(self):
        return self._is_loaded

    @property
    def is_invalidated(self):
        return self._is_invalidated

    def _build_ui(self):
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

        layout.addWidget(self.top_bar)
        layout.addWidget(self.scroll_area, 1)

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
        scroll_bar = self.scroll_area.verticalScrollBar()
        previous_scroll = scroll_bar.value() if preserve_scroll else 0
        target_scroll = 0 if reset_scroll else previous_scroll

        self._prepare_scroll_restore(target_scroll)

        with get_connection() as conn:
            entries = load_default_history_entries(conn)

        self.entries = list(entries)
        self._render_entries()
        self._is_loaded = True
        self._is_invalidated = False
        self._set_status_message(_format_entry_count(len(self.entries)))

        if target_scroll == 0:
            scroll_bar.setValue(0)
            QTimer.singleShot(0, lambda: scroll_bar.setValue(0))

        return self.entries

    def _prepare_scroll_restore(self, target_scroll):
        scroll_bar = self.scroll_area.verticalScrollBar()

        if self._scroll_restore_callback is not None:
            try:
                scroll_bar.rangeChanged.disconnect(
                    self._scroll_restore_callback
                )
            except (RuntimeError, TypeError):
                pass

            self._scroll_restore_callback = None

        if target_scroll <= 0:
            return

        def restore_when_range_is_ready(minimum, maximum):
            if maximum <= minimum:
                return

            scroll_bar.setValue(
                max(minimum, min(target_scroll, maximum))
            )

            try:
                scroll_bar.rangeChanged.disconnect(
                    restore_when_range_is_ready
                )
            except (RuntimeError, TypeError):
                pass

            if self._scroll_restore_callback is restore_when_range_is_ready:
                self._scroll_restore_callback = None

        self._scroll_restore_callback = restore_when_range_is_ready
        scroll_bar.rangeChanged.connect(restore_when_range_is_ready)

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
                "is_collection_pick": entry.is_collection_pick,
            }

        self.entries_layout.addStretch(1)

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
            "is_collection_pick": state.get("is_collection_pick"),
        }
        self._confirmed_states[media_id] = normalized_state
        self.entries = [
            replace(
                entry,
                watch_state=normalized_state["watch_state"],
                impression=normalized_state["impression"],
                is_collection_pick=normalized_state[
                    "is_collection_pick"
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
                normalized_state["is_collection_pick"],
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
    return f"{count} watched {noun}"
