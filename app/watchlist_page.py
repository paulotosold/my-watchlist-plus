from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.filtered_media import FilteredMedia
from app.library_filter import DEFAULT_FILTER_TEXT
from app.media_board import MediaBoard
from app.top_bar import TopBar


class WatchlistPage(QWidget):
    status_message_changed = Signal(str)
    find_media_requested = Signal(str)
    details_requested = Signal(object)
    library_changed = Signal()

    def __init__(self, parent=None, *, rows=2, columns=5):
        super().__init__(parent)

        self._is_loaded = False
        self._is_invalidated = True
        self._status_message = ""

        self.top_bar = TopBar(
            filter_label_text="Filter Library:",
            default_filter_text=DEFAULT_FILTER_TEXT,
        )
        self.media_board = MediaBoard(rows=rows, columns=columns)
        self.filtered_media = FilteredMedia()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.top_bar)
        layout.addWidget(self.media_board, 1)

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

    def ensure_loaded(self):
        if not self._is_loaded or self._is_invalidated:
            self.refresh_media_view()

        return self.filtered_media.media_list

    def invalidate(self):
        self._is_invalidated = True

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

    def _set_status_message(self, message):
        self._status_message = message
        self.status_message_changed.emit(message)
