from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from app.find_media_handler import handle_find_media_input
from app.filtered_media import FilteredMedia
from app.library_filter import DEFAULT_FILTER_TEXT
from app.media_board import MediaBoard
from app.top_bar import TopBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("My Watchlist+")
        self.setFixedSize(1440, 900)

        central_widget = QWidget()
        central_widget.setObjectName("central-widget")
        central_widget.setStyleSheet("#central-widget {background-color: #F1F1F1;}")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)

        self.top_bar = TopBar()
        self.top_bar.filter_submitted.connect(self.on_filter_input)
        self.top_bar.find_media_submitted.connect(self.on_find_media_input)
        main_layout.addWidget(self.top_bar)

        self.media_board = MediaBoard(rows=2, columns=5)
        main_layout.addWidget(self.media_board, 1)

        self.status_bar = self.statusBar()

        self.filtered_media = FilteredMedia()
        self.filtered_media.refresh()

        self.media_board.load_media(self.filtered_media)
        self._update_status_bar()

    def on_filter_input(self, filter_text):
        if filter_text != DEFAULT_FILTER_TEXT:
            print("Filter Library:", filter_text)
            return

        self.filtered_media = FilteredMedia()
        self.refresh_media_view()

    def on_find_media_input(self, media_query):
        print("Find Media:", media_query)
        result = handle_find_media_input(self, media_query)

        if result and result.get("status") in {"saved", "deleted"}:
            self.refresh_media_view()

    def refresh_media_view(self):
        self.filtered_media.refresh()
        self.media_board.load_media(self.filtered_media)
        self._update_status_bar()

    def _update_status_bar(self):
        self.status_bar.showMessage(f"{len(self.filtered_media.media_list)} filtered media")
