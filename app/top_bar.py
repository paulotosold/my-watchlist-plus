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

ADD_INPUT_PLACEHOLDER = "IMDb ID or describe what you’re looking for"

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
        self.add_input.setPlaceholderText(ADD_INPUT_PLACEHOLDER)
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
