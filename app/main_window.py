from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from app.filtered_media import FilteredMedia
from app.media_board import MediaBoard
from app.top_bar import TopBar
from app.media_input_handler import handle_media_input


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
        self.top_bar.search_input.setPlaceholderText(
            "all suggested, to watch, or watching media in random order"
        )
        self.top_bar.search_submitted.connect(self.on_search_input)
        self.top_bar.add_submitted.connect(self.on_add_input)
        main_layout.addWidget(self.top_bar)

        self.media_board = MediaBoard(rows=2, columns=5)
        main_layout.addWidget(self.media_board, 1)

        self.status_bar = self.statusBar()

        self.filtered_media = FilteredMedia()
        self.filtered_media.refresh()

        self.media_board.load_media(self.filtered_media)
        self._update_status_bar()

    def on_search_input(self, search_query):
        print("Search:", search_query)
        self.refresh_media_view()

    def on_add_input(self, input_query):
        print("Add:", input_query)
        result = handle_media_input(self, input_query)

        if result and result.get("status") in {"saved", "deleted"}:
            self.refresh_media_view()

    def refresh_media_view(self):
        self.filtered_media.refresh()
        self.media_board.load_media(self.filtered_media)
        self._update_status_bar()

    def _update_status_bar(self):
        self.status_bar.showMessage(f"{len(self.filtered_media.media_list)} filtered media")
