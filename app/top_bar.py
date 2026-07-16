from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from app.library_filter import DEFAULT_FILTER_TEXT

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

FIND_MEDIA_INPUT_PLACEHOLDER = "IMDb ID or describe what you’re looking for"


class TopBar(QWidget):
    filter_submitted = Signal(str)
    find_media_submitted = Signal(str)

    def __init__(
        self,
        parent=None,
        *,
        filter_label_text="Filter Library:",
        default_filter_text=DEFAULT_FILTER_TEXT,
        find_media_label_text="Find Media:",
        find_media_placeholder=FIND_MEDIA_INPUT_PLACEHOLDER,
    ):
        super().__init__(parent)

        self.filter_label_text = filter_label_text
        self.default_filter_text = default_filter_text
        self.find_media_label_text = find_media_label_text
        self.find_media_placeholder = find_media_placeholder

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        input_box_height = 32
        icon_size = 20

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.filter_label = QLabel(self.filter_label_text)

        self.filter_input = QLineEdit()
        self.filter_input.setFixedHeight(input_box_height)
        self.filter_input.setText(self.default_filter_text)
        self.filter_input.setStyleSheet(INPUT_BOX_STYLE)

        self.filter_button = QToolButton()
        self.filter_button.setIcon(QIcon("app/assets/top_bar_filter.png"))
        self.filter_button.setIconSize(QSize(icon_size, icon_size))
        self.filter_button.setCursor(Qt.PointingHandCursor)
        self.filter_button.setStyleSheet(BUTTON_STYLE)

        self.find_media_label = QLabel(self.find_media_label_text)

        self.find_media_input = QLineEdit()
        self.find_media_input.setFixedHeight(input_box_height)
        self.find_media_input.setPlaceholderText(self.find_media_placeholder)
        self.find_media_input.setStyleSheet(INPUT_BOX_STYLE)

        layout.addWidget(self.filter_label)
        layout.addWidget(self.filter_input, 1)
        layout.addWidget(self.filter_button)
        layout.addWidget(self.find_media_label)
        layout.addWidget(self.find_media_input, 1)

    def _connect_signals(self):
        self.filter_input.returnPressed.connect(self._emit_filter)
        self.find_media_input.returnPressed.connect(self._emit_find_media)

    def _emit_filter(self):
        self.filter_submitted.emit(self.filter_input.text())

    def _emit_find_media(self):
        text = self.find_media_input.text().strip()
        self.find_media_submitted.emit(text)
