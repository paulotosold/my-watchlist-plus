from __future__ import annotations

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app.ui.top_bar import TopBar

from .board import DEFAULT_POSTERS_PER_ROW, MediaBoard
from .filtering import DEFAULT_FILTER_TEXT, FilteredMedia


WATCHLIST_BACKGROUND_COLOR = "#F1F1F1"


class WatchlistPage(QWidget):
    status_message_changed = Signal(str)
    watchlist_state_changed = Signal(int, int, bool)
    find_media_requested = Signal(str)
    details_requested = Signal(object)
    library_changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        posters_per_row=DEFAULT_POSTERS_PER_ROW,
    ):
        super().__init__(parent)

        self._is_loaded = False
        self._is_invalidated = True
        self._status_message = ""
        self._pending_scroll_anchor = None
        self._scroll_anchor_to_restore = None
        self._filtered_scroll_anchor = None
        self._last_viewport_width = None

        self.top_bar = TopBar(
            filter_label_text="Filter Library:",
            default_filter_text=DEFAULT_FILTER_TEXT,
        )
        self.media_board = MediaBoard(
            posters_per_row=posters_per_row,
        )
        self._last_pinned_only = self.media_board.pinned_only
        self.filtered_media = FilteredMedia()

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("watchlistScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.viewport().setObjectName(
            "watchlistScrollViewport"
        )
        self.media_board.setObjectName("watchlistScrollContent")
        self.scroll_area.setStyleSheet(
            f"""
            QScrollArea#watchlistScrollArea,
            QWidget#watchlistScrollViewport,
            QWidget#watchlistScrollContent {{
                background-color: {WATCHLIST_BACKGROUND_COLOR};
            }}
            """
        )
        self.scroll_area.setWidget(self.media_board)
        self.scroll_area.viewport().installEventFilter(self)
        self.media_board.set_layout_width(self._stable_board_width())

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_viewport_resize)

        self._anchor_restore_timer = QTimer(self)
        self._anchor_restore_timer.setSingleShot(True)
        self._anchor_restore_timer.timeout.connect(
            self._apply_pending_scroll_anchor
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.top_bar)
        layout.addWidget(self.scroll_area, 1)

        self.top_bar.filter_submitted.connect(self.on_filter_input)
        self.top_bar.find_media_submitted.connect(
            self.find_media_requested.emit
        )
        self.media_board.details_requested.connect(
            self.details_requested.emit
        )
        self.media_board.view_state_changed.connect(
            self._on_board_view_state_changed
        )

        self.ensure_loaded()

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
        return self.media_board.posters_per_row

    @property
    def filtered_count(self):
        return len(self.media_board.cards)

    @property
    def pinned_count(self):
        return self.media_board.pinned_count

    @property
    def pinned_only(self):
        return self.media_board.pinned_only

    def ensure_loaded(self):
        if not self._is_loaded or self._is_invalidated:
            self.refresh_media_view()

        return self.filtered_media.media_list

    def invalidate(self):
        self._is_invalidated = True

    def clear_find_media_query(self):
        self.top_bar.find_media_input.clear()

    def set_posters_per_row(self, posters_per_row):
        anchor = self._capture_scroll_anchor()
        changed = self.media_board.set_posters_per_row(posters_per_row)

        if changed:
            self._restore_scroll_anchor_later(anchor)

        return changed

    def set_pinned_only(self, pinned_only):
        pinned_only = bool(pinned_only)

        if pinned_only == self.pinned_only:
            return False

        self._cancel_pending_scroll_restore()
        self._pending_scroll_anchor = None

        if pinned_only:
            self._filtered_scroll_anchor = (
                self._capture_filtered_scroll_anchor()
            )

        changed = self.media_board.set_pinned_only(pinned_only)

        if not changed:
            if pinned_only:
                self._filtered_scroll_anchor = None
            return False

        return True

    def clear_all_pins(self):
        was_pinned_only = self.pinned_only

        if was_pinned_only:
            self._cancel_pending_scroll_restore()

        changed = self.media_board.clear_all_pins()

        if was_pinned_only and self.pinned_only:
            self.scroll_area.verticalScrollBar().setValue(0)

        return changed

    def reload_default_filter(self):
        if self.pinned_only:
            self.set_pinned_only(False)

        self.filtered_media = FilteredMedia()
        self._is_invalidated = True
        self.refresh_media_view()

    def on_filter_input(self, filter_text):
        if filter_text != DEFAULT_FILTER_TEXT:
            print("Filter Library:", filter_text)
            return

        return self.reload_default_filter()

    def refresh_media_view(self):
        self.filtered_media.refresh()
        self.media_board.load_media(self.filtered_media)
        self._is_loaded = True
        self._is_invalidated = False

    def refresh_preserving_grid(self):
        previous_media = list(self.filtered_media.media_list)
        anchor = self._capture_scroll_anchor()

        self.filtered_media.refresh()
        self.media_board.reconcile_media(
            self.filtered_media,
            previous_media,
        )
        self._is_loaded = True
        self._is_invalidated = False
        self._restore_scroll_anchor_later(anchor)
        return self.filtered_media.media_list

    def _on_board_view_state_changed(
        self,
        filtered_count,
        pinned_count,
        pinned_only,
    ):
        was_pinned_only = self._last_pinned_only
        self._last_pinned_only = pinned_only

        if pinned_only and not was_pinned_only:
            self._pending_scroll_anchor = None
            self._cancel_pending_scroll_restore()
            self.scroll_area.verticalScrollBar().setValue(0)
        elif was_pinned_only and not pinned_only:
            self._pending_scroll_anchor = None
            self._cancel_pending_scroll_restore()
            anchor = self._filtered_scroll_anchor
            self._filtered_scroll_anchor = None
            self._restore_filtered_scroll_anchor_later(anchor)

        title_label = "title" if filtered_count == 1 else "titles"
        self._set_status_message(
            f"{filtered_count} filtered {title_label}"
        )
        self.watchlist_state_changed.emit(
            filtered_count,
            pinned_count,
            pinned_only,
        )

    def eventFilter(self, watched, event):
        if (
            watched is self.scroll_area.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            viewport_width = event.size().width()

            if viewport_width != self._last_viewport_width:
                self._pending_scroll_anchor = self._capture_scroll_anchor()
                self._last_viewport_width = viewport_width
                self._resize_timer.start(0)

        return super().eventFilter(watched, event)

    def _apply_viewport_resize(self):
        anchor = self._pending_scroll_anchor
        self._pending_scroll_anchor = None
        self.media_board.set_layout_width(self._stable_board_width())
        self.media_board.reflow_cards()
        self._restore_scroll_anchor_later(anchor)

    def _stable_board_width(self):
        viewport_width = self.scroll_area.viewport().width()

        if (
            self.scroll_area.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        ):
            return viewport_width

        scroll_bar = self.scroll_area.verticalScrollBar()
        is_transient = bool(
            self.scroll_area.style().styleHint(
                QStyle.StyleHint.SH_ScrollBar_Transient,
                None,
                scroll_bar,
            )
        )

        if is_transient or scroll_bar.isVisibleTo(self.scroll_area):
            return viewport_width

        return max(
            1,
            viewport_width - scroll_bar.sizeHint().width(),
        )

    def _capture_scroll_anchor(self):
        visible_cards = list(self.media_board.visible_cards)

        if not visible_cards:
            return None

        scroll_value = self.scroll_area.verticalScrollBar().value()

        for card in visible_cards:
            if card.geometry().bottom() >= scroll_value:
                return card, scroll_value - card.geometry().top()

        return None

    def _capture_filtered_scroll_anchor(self):
        visible_anchor = self._capture_scroll_anchor()

        if visible_anchor is None:
            return None

        card, offset = visible_anchor

        try:
            canonical_index = self.media_board.cards.index(card)
        except ValueError:
            return None

        return (
            card,
            canonical_index,
            offset,
            self.scroll_area.verticalScrollBar().value(),
        )

    def _restore_scroll_anchor_later(self, anchor):
        if anchor is None:
            return

        self._scroll_anchor_to_restore = ("visible", anchor)
        self._anchor_restore_timer.start(0)

    def _restore_filtered_scroll_anchor_later(self, anchor):
        if anchor is None:
            return

        self._scroll_anchor_to_restore = ("filtered", anchor)
        self._anchor_restore_timer.start(0)

    def _cancel_pending_scroll_restore(self):
        if self._anchor_restore_timer.isActive():
            self._anchor_restore_timer.stop()

        self._scroll_anchor_to_restore = None

    def _apply_pending_scroll_anchor(self):
        pending_restore = self._scroll_anchor_to_restore
        self._scroll_anchor_to_restore = None

        if pending_restore is None:
            return

        restore_kind, anchor = pending_restore

        if restore_kind == "filtered":
            self._restore_filtered_scroll_anchor(anchor)
        else:
            self._restore_scroll_anchor(anchor)

    def _restore_scroll_anchor(self, anchor):
        card, offset = anchor

        if card not in self.media_board.visible_cards:
            return

        target_value = card.geometry().top() + offset
        self._set_scroll_value(target_value)

    def _restore_filtered_scroll_anchor(self, anchor):
        card, canonical_index, offset, scroll_value = anchor
        canonical_cards = self.media_board.cards

        if card in canonical_cards:
            target_card = card
        elif canonical_cards:
            target_index = min(canonical_index, len(canonical_cards) - 1)
            target_card = canonical_cards[target_index]
        else:
            target_card = None

        target_value = (
            target_card.geometry().top() + offset
            if target_card is not None
            else scroll_value
        )
        self._set_scroll_value(target_value)

    def _set_scroll_value(self, target_value):
        scroll_bar = self.scroll_area.verticalScrollBar()
        scroll_bar.setValue(
            max(
                scroll_bar.minimum(),
                min(target_value, scroll_bar.maximum()),
            )
        )

    def _set_status_message(self, message):
        self._status_message = message
        self.status_message_changed.emit(message)
