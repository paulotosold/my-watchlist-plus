from __future__ import annotations

import calendar

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QToolButton,
    QVBoxLayout,
)


class CleanCalendarPopup(QFrame):
    date_selected = Signal(QDate)

    DAY_BUTTON_WIDTH = 38
    DAY_BUTTON_HEIGHT = 28
    NAV_BUTTON_WIDTH = 28
    NAV_BUTTON_HEIGHT = 26
    GRID_SPACING = 4

    def __init__(self, initial_date: QDate | None = None, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.current_date = (
            initial_date
            if initial_date is not None and initial_date.isValid()
            else QDate.currentDate()
        )
        self.view_year = self.current_date.year()
        self.view_month = self.current_date.month()

        self.setObjectName("calendarPopup")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 10)
        main_layout.setSpacing(6)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        header_layout = QHBoxLayout()

        self.prev_button = QToolButton(self)
        self.prev_button.setText("‹")
        self.prev_button.setObjectName("navButton")
        self.prev_button.setFixedSize(
            self.NAV_BUTTON_WIDTH,
            self.NAV_BUTTON_HEIGHT,
        )
        self.prev_button.clicked.connect(self.previous_month)

        self.month_label = QLabel(self)
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.month_label.setObjectName("monthLabel")

        self.next_button = QToolButton(self)
        self.next_button.setText("›")
        self.next_button.setObjectName("navButton")
        self.next_button.setFixedSize(
            self.NAV_BUTTON_WIDTH,
            self.NAV_BUTTON_HEIGHT,
        )
        self.next_button.clicked.connect(self.next_month)

        header_layout.addWidget(self.prev_button)
        header_layout.addWidget(self.month_label, stretch=1)
        header_layout.addWidget(self.next_button)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(self.GRID_SPACING)
        self.grid.setVerticalSpacing(self.GRID_SPACING)

        main_layout.addLayout(header_layout)
        main_layout.addLayout(self.grid)

        self.setStyleSheet("""
            QFrame#calendarPopup {
                background: white;
                border: 1px solid #D0D0D0;
                border-radius: 0px;
            }

            QLabel#monthLabel {
                font-size: 13px;
                font-weight: 700;
                color: #222;
            }

            QToolButton {
                border: none;
                border-radius: 6px;
                background: transparent;
                padding: 0px;
                margin: 0px;
                font-size: 12px;
                color: #222;
            }

            QToolButton:hover {
                background: #EEF3FF;
            }

            QToolButton#navButton {
                font-size: 18px;
                font-weight: 500;
            }

            QToolButton#dayButton {
                background: #F8F8F8;
                border: 1px solid #E3E3E3;
            }

            QToolButton#dayButton:hover {
                background: #EAF0FF;
                border: 1px solid #BFD0FF;
            }

            QToolButton#selectedDay {
                background: #2F6FED;
                color: white;
                border: 1px solid #2F6FED;
                font-weight: 700;
            }

            QToolButton#outsideMonth {
                color: #B8B8B8;
                background: transparent;
                border: 1px solid transparent;
            }

            QLabel#weekdayLabel {
                color: #777;
                font-size: 10px;
                font-weight: 700;
            }
        """)

        self.rebuild()

    def previous_month(self):
        if self.view_month == 1:
            self.view_month = 12
            self.view_year -= 1
        else:
            self.view_month -= 1

        self.rebuild()

    def next_month(self):
        if self.view_month == 12:
            self.view_month = 1
            self.view_year += 1
        else:
            self.view_month += 1

        self.rebuild()

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def rebuild(self):
        self.clear_grid()

        month_name = QDate(self.view_year, self.view_month, 1).toString(
            "MMMM yyyy"
        )
        self.month_label.setText(month_name)

        for column, name in enumerate(
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        ):
            label = QLabel(name, self)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName("weekdayLabel")
            label.setFixedWidth(self.DAY_BUTTON_WIDTH)
            self.grid.addWidget(label, 0, column)

        month_days = calendar.Calendar(firstweekday=0).monthdatescalendar(
            self.view_year,
            self.view_month,
        )

        for row, week in enumerate(month_days, start=1):
            for column, python_date in enumerate(week):
                date = QDate(
                    python_date.year,
                    python_date.month,
                    python_date.day,
                )
                button = QToolButton(self)
                button.setText(str(python_date.day))
                button.setFixedSize(
                    self.DAY_BUTTON_WIDTH,
                    self.DAY_BUTTON_HEIGHT,
                )
                button.setCursor(Qt.CursorShape.PointingHandCursor)

                if date == self.current_date:
                    button.setObjectName("selectedDay")
                elif python_date.month != self.view_month:
                    button.setObjectName("outsideMonth")
                else:
                    button.setObjectName("dayButton")

                button.clicked.connect(
                    lambda checked=False, selected_date=date: self.choose_date(
                        selected_date
                    )
                )
                self.grid.addWidget(button, row, column)

    def choose_date(self, date: QDate):
        self.current_date = date
        self.date_selected.emit(date)
