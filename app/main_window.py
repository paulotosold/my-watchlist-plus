from PySide6.QtWidgets import QGridLayout, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtGui import QIcon

from app.media_board import MediaBoard
from app.top_bar import TopBar
from app.media_session import MediaSession
from _local.media_list_test import media_list_test
from app.media_input_handler import handle_media_input


class FilteredMedia:
    def __init__(self):
        self.filter_parameters = {}
        self.media_list = []
        self.next_media_index = 0

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        #self.setWindowIcon(QIcon("app/assets/mrflick.png"))

        self.setWindowTitle("My Watchlist+")
        #self.setWindowIcon(QIcon("app/assets/mrflick.png"))
        self.setFixedSize(1440, 900)

        central_widget = QWidget()
        central_widget.setObjectName("central-widget")
        central_widget.setStyleSheet("#central-widget {background-color: #F1F1F1;}")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)

        self.top_bar = TopBar()
        self.top_bar.search_submitted.connect(self.on_search_input)
        self.top_bar.add_submitted.connect(self.on_add_input)
        main_layout.addWidget(self.top_bar)

        self.media_board = MediaBoard(rows=2, columns=5)
        main_layout.addWidget(self.media_board, 1)

        self.status_bar = self.statusBar() #self.status_bar.showMessage("125 filtered media")

        self.filtered_media = FilteredMedia()
        self.filtered_media.media_list = media_list_test

        self.media_board.load_media(self.filtered_media)

    def on_search_input(self, search_query):
        print("Search:", search_query)
        self.media_board.set_grid_size(3, 3)
        self.media_board.load_media(self.filtered_media)

    def on_add_input(self, input_query):
        print("Add:", input_query)
        handle_media_input(self, input_query)
        # call formulário já semi preenchido por uma llm
        # entry_draft = media_input_resolver.resolve_input(self.add_input.text())
        # self.watch_entry_dialog.show(entry_draft) WatchEntryDialog ou WatchEntryDialog ou WatchEntryEditor