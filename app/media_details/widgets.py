from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
)

from .constants import (
    DETAIL_ICON_BUTTON_SIZE,
    DETAIL_ICON_DIR,
    DETAIL_ICON_SIZE,
)


DETAIL_HEADER_ICON_TEXT_SPACING = 1


def make_icon_button(icon_name, parent=None, callback=None):
    button = QToolButton(parent)
    button.setFixedSize(DETAIL_ICON_BUTTON_SIZE, DETAIL_ICON_BUTTON_SIZE)
    button.setIcon(QIcon(str(DETAIL_ICON_DIR / icon_name)))
    button.setIconSize(QSize(DETAIL_ICON_SIZE, DETAIL_ICON_SIZE))
    button.setCursor(Qt.CursorShape.PointingHandCursor)

    if callback is not None:
        button.clicked.connect(callback)

    return button


class DetailBlock(QFrame):
    def __init__(self, title, icon_name=None, parent=None):
        super().__init__(parent)

        self.setObjectName("detailBlock")
        self.action_button = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 10, 12, 12)
        self.main_layout.setSpacing(5)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(DETAIL_HEADER_ICON_TEXT_SPACING)

        if icon_name:
            self.action_button = make_icon_button(icon_name, self)
            header_layout.addWidget(self.action_button)

        title_label = QLabel(title, self)
        title_label.setObjectName("blockTitle")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(3)

        self.main_layout.addLayout(header_layout)
        self.main_layout.addLayout(self.body_layout, stretch=1)


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        widget = item.widget()

        if child_layout is not None:
            clear_layout(child_layout)

        if widget is not None:
            widget.deleteLater()
