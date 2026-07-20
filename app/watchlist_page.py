from __future__ import annotations

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app.filtered_media import FilteredMedia
from app.library_filter import DEFAULT_FILTER_TEXT
from app.media_board import DEFAULT_POSTERS_PER_ROW, MediaBoard
from app.top_bar import TopBar


WATCHLIST_BACKGROUND_COLOR = "#F1F1F1"


class WatchlistPage(QWidget):
    status_message_changed = Signal(str)
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
        self._last_viewport_width = None

        self.top_bar = TopBar(
            filter_label_text="Filter Library:",
            default_filter_text=DEFAULT_FILTER_TEXT,
        )
        self.media_board = MediaBoard(
            posters_per_row=posters_per_row,
        )
        self.filtered_media = FilteredMedia()

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("watchlistScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
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

    def ensure_loaded(self):
        if not self._is_loaded or self._is_invalidated:
            self.refresh_media_view()

        return self.filtered_media.media_list

    def invalidate(self):
        self._is_invalidated = True

    def set_posters_per_row(self, posters_per_row):
        anchor = self._capture_scroll_anchor()
        changed = self.media_board.set_posters_per_row(posters_per_row)

        if changed:
            self._restore_scroll_anchor_later(anchor)

        return changed

    def on_filter_input(self, filter_text):
        if filter_text != DEFAULT_FILTER_TEXT:
            print("Filter Library:", filter_text)
            return

        self.filtered_media = FilteredMedia()
        self._is_invalidated = True
        self.refresh_media_view()

    def refresh_media_view(self):
        self.filtered_media.refresh()
        self.media_board.load_media(self.filtered_media)
        self._is_loaded = True
        self._is_invalidated = False
        self._set_status_message(
            f"{len(self.filtered_media.media_list)} filtered media"
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
        if not self.media_board.cards:
            return None

        scroll_value = self.scroll_area.verticalScrollBar().value()

        for card in self.media_board.cards:
            if card.geometry().bottom() >= scroll_value:
                return card, scroll_value - card.geometry().top()

        return None

    def _restore_scroll_anchor_later(self, anchor):
        if anchor is None:
            return

        self._scroll_anchor_to_restore = anchor
        self._anchor_restore_timer.start(0)

    def _apply_pending_scroll_anchor(self):
        anchor = self._scroll_anchor_to_restore
        self._scroll_anchor_to_restore = None

        if anchor is not None:
            self._restore_scroll_anchor(anchor)

    def _restore_scroll_anchor(self, anchor):
        card, offset = anchor

        if card not in self.media_board.cards:
            return

        scroll_bar = self.scroll_area.verticalScrollBar()
        target_value = card.geometry().top() + offset
        scroll_bar.setValue(
            max(
                scroll_bar.minimum(),
                min(target_value, scroll_bar.maximum()),
            )
        )

    def _set_status_message(self, message):
        self._status_message = message
        self.status_message_changed.emit(message)
