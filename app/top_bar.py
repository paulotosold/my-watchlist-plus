import random

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

BUTTON_STYLE = """
QToolButton {
    background-color: white;
    color: black;
    border: 1px solid #bcbcbc;
    border-radius: 6px;
    padding: 3px 3px;
}
QToolButton:hover {
    background-color: #f2f2f2;
}
"""

INPUT_BOX_STYLE = """
QLineEdit {
    border: 1px solid #bcbcbc;
    border-radius: 16px;
    padding: 4px 8px;
    background-color: white;
}
"""

ADD_INPUT_EXAMPLES = [
    "Watched 'Project Hail Mary' in the theater yesterday. Great movie!",
    "Add 'Dune: Part Two' to my watchlist.",
    "Watched 'The Batman' last night and loved the atmosphere.",
    "Add 'Severance' to my series watchlist.",
    "Finished season 1 of 'The Bear' this weekend.",
    "Add 'Blade Runner 2049' to rewatch later.",
    "Watched 'Arrival' again yesterday. Still amazing.",
    "Add 'The Last of Us' to my series watchlist.",
    "Watched episode 3 of 'Andor' last night.",
    "Finished 'Shogun' and give it 5 stars.",
    "Add 'The Matrix' as a must-rewatch.",
    "Watched 'Spirited Away' with Benji today.",
    "Add 'Spider-Man: Across the Spider-Verse' for family movie night.",
    "Watched 'Poor Things' last Friday. Weird but brilliant.",
    "Add 'The Wild Robot' to watch with Benji.",
    "Watched 'Interstellar' again. Big feelings, bigger organs.",
    "Add 'Mad Max: Fury Road' to my action rewatch list.",
    "Started 'Slow Horses' and liked the first episode.",
    "Watched 'The Godfather' for the first time.",
    "Add 'Paddington 2' because apparently everyone says it's perfect.",
    "Watched 'Oppenheimer' in IMAX.",
    "Add 'Past Lives' to watch soon.",
    "Finished 'Succession' season 2.",
    "Watched 'The Holdovers' yesterday. Cozy and sad in a good way.",
    "Add 'Alien' to my Halloween watchlist.",
    "Watched 'Nope' last night. Not sure what I think yet.",
    "Add 'Mission: Impossible – Fallout' to rewatch.",
    "Watched 'Ratatouille' with the family today.",
    "Add 'Wall-E' for a Sunday afternoon.",
    "Finished 'Dark' season 1 and need a diagram for my brain.",
    "Watched 'The Grand Budapest Hotel' again.",
    "Add 'Everything Everywhere All at Once' to favorites.",
    "Watched 'John Wick: Chapter 4' yesterday. Exhausting, in a good way.",
    "Add 'The Iron Giant' to watch with Benji.",
    "Started 'Foundation' but only watched the pilot.",
    "Watched 'Heat' last night. Great diner scene.",
    "Add 'The Boy and the Heron' to watch later.",
    "Finished 'Chernobyl'. Incredible, but heavy.",
    "Watched 'Knives Out' again. Still fun.",
    "Add 'The Nice Guys' to my comedy list.",
    "Watched 'The Social Network' yesterday and give it 4.5 stars.",
    "Add 'Children of Men' to rewatch soon.",
    "Add 'Silo' to my series watchlist.",
    "Watched 'Toy Story' with Benji this afternoon.",
    "Add 'The Incredibles' for family movie night.",
    "Finished 'Blue Eye Samurai' and loved the animation.",
    "Watched 'Her' last night. Beautiful and uncomfortable.",
    "Add 'Casablanca' because I still haven't seen it.",
    "Watched 'Princess Mononoke' again.",
    "Add 'The Prestige' to rewatch with fresh eyes.",
]

class TopBar(QWidget):
    search_submitted = Signal(str)
    add_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        input_box_height = 32
        icon_size = 20

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.search_label = QLabel("Search Library:")

        self.search_input = QLineEdit()
        self.search_input.setFixedHeight(input_box_height)
        self.search_input.setStyleSheet(INPUT_BOX_STYLE)

        self.search_btn = QToolButton()
        self.search_btn.setIcon(QIcon("app/assets/top_bar_icons/lupe.png"))
        self.search_btn.setIconSize(QSize(icon_size, icon_size))
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.setStyleSheet(BUTTON_STYLE)

        self.add_label = QLabel("Add to Watchlist:")

        self.add_input = QLineEdit()
        self.add_input.setFixedHeight(input_box_height)
        self.add_input.setPlaceholderText(random.choice(ADD_INPUT_EXAMPLES))
        self.add_input.setStyleSheet(INPUT_BOX_STYLE)

        self.add_btn = QToolButton()
        self.add_btn.setIcon(QIcon("app/assets/top_bar_icons/add.png"))
        self.add_btn.setIconSize(QSize(icon_size, icon_size))
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet(BUTTON_STYLE)

        layout.addWidget(self.search_label)
        layout.addWidget(self.search_input, 1)
        layout.addWidget(self.search_btn)
        layout.addWidget(self.add_label)
        layout.addWidget(self.add_input, 1)
        layout.addWidget(self.add_btn)

    def _connect_signals(self):
        self.search_input.returnPressed.connect(self._emit_search)
        self.search_btn.clicked.connect(self._emit_search)

        self.add_input.returnPressed.connect(self._emit_add)
        self.add_btn.clicked.connect(self._emit_add)

    def _emit_search(self):
        text = self.search_input.text().strip()
        self.search_submitted.emit(text)

    def _emit_add(self):
        text = self.add_input.text().strip()
        self.add_submitted.emit(text)
