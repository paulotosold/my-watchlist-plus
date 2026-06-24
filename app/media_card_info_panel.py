from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QWidget
)


class MediaCardInfoPanel(QFrame):
    edit_clicked = Signal()
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._create_widgets()
        self._build_layout()
        self._connect_signals()
        self._apply_styles()

    def _create_widgets(self):
        self.setObjectName("infoPanel")

        self.title_value = QLabel(self)
        self.title_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.title_value.setWordWrap(True)

        self.poster_image = QLabel(self)
        self.poster_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_image.setScaledContents(False)
        self.poster_image.setFixedSize(94, 140)

        self.year_label = QLabel("Year:", self)
        self.year_value = QLabel(self)

        self.duration_label = QLabel("Duration:", self)
        self.duration_value = QLabel(self)

        self.status_label = QLabel("Status:", self)
        self.status_value = QLabel(self)

        self.impression_label = QLabel("Impression:", self)
        self.impression_value = QLabel(self)

        self.streaming_label = QLabel("Streaming at:", self)
        self.streaming_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.streaming_value = QLabel(self)
        self.streaming_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.streaming_value.setWordWrap(True)

        self.btn_edit = QPushButton("Edit", self)
        self.btn_close = QPushButton("Back", self)

        self.btn_edit.setMinimumHeight(32)
        self.btn_close.setMinimumHeight(32)

    def _make_info_row(self, label_widget, value_widget):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        row.addWidget(label_widget, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        row.addWidget(value_widget, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        row.addStretch()

        return row

    def _build_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 16, 32, 16)
        main_layout.setSpacing(8)

        poster_layout = QHBoxLayout()
        poster_layout.setContentsMargins(0, 0, 0, 0)
        poster_layout.addWidget(self.poster_image)
        poster_layout.addStretch()

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        self.info_top_gap = QWidget(self)
        self.info_top_gap.setFixedHeight(8) #space between poster ↔ infos

        info_layout.addWidget(self.info_top_gap)
        info_layout.addLayout(self._make_info_row(self.year_label, self.year_value))
        info_layout.addLayout(self._make_info_row(self.duration_label, self.duration_value))
        info_layout.addLayout(self._make_info_row(self.status_label, self.status_value))
        info_layout.addLayout(self._make_info_row(self.impression_label, self.impression_value))
        #info_layout.addLayout(self._make_info_row(self.notes_label, self.notes_value))

        streaming_layout = QVBoxLayout()
        streaming_layout.setContentsMargins(0, 0, 0, 0)
        streaming_layout.setSpacing(2)
        streaming_layout.addWidget(self.streaming_label)
        streaming_layout.addWidget(self.streaming_value)

        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 0, 0, 0)
        buttons_row.setSpacing(10)
        buttons_row.addWidget(self.btn_edit, 1)
        buttons_row.addWidget(self.btn_close, 1)

        main_layout.addWidget(self.title_value)
        main_layout.addLayout(poster_layout)
        main_layout.addLayout(info_layout)
        main_layout.addStretch()
        main_layout.addLayout(streaming_layout)
        main_layout.addSpacing(12)
        main_layout.addLayout(buttons_row)

    def _connect_signals(self):
        self.btn_close.clicked.connect(self.back_clicked.emit)
        self.btn_edit.clicked.connect(self.edit_clicked.emit)

    def _apply_styles(self):
        self.setStyleSheet("""
            #infoPanel {
                background-color: white;
                border: 1px solid #cfcfcf;
                border-radius: 0px;
            }

            QLabel {
                color: black;
                font-size: 13px;
                background: transparent;
            }

            QPushButton {
                background-color: white;
                color: black;
                border: 1px solid #bcbcbc;
                border-radius: 6px;
                padding: 6px 12px;
            }

            QPushButton:hover {
                background-color: #f2f2f2;
            }
        """)

        self.title_value.setStyleSheet("""
            color: black;
            font-size: 15px;
            font-weight: bold;
            background: transparent;
        """)

        self.streaming_label.setStyleSheet("""
            color: black;
            font-size: 13px;
            font-weight: normal;
            background: transparent;
        """)

        self.streaming_value.setStyleSheet("""
            color: black;
            font-size: 13px;
            background: transparent;
        """)

        self.poster_image.setStyleSheet("""
            background-color: #dcdcdc;
            color: #666666;
            border: none;
            border-radius: 0px;
        """)
