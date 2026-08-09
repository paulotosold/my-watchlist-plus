import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog, QToolButton

from app.media_details.calendar_picker import CleanCalendarPopup


class CleanCalendarPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.application.processEvents()

    def test_uses_valid_initial_date_and_falls_back_to_today(self):
        selected_date = QDate(2026, 7, 14)
        popup = CleanCalendarPopup(selected_date)

        self.assertEqual(popup.current_date, selected_date)
        self.assertEqual((popup.view_year, popup.view_month), (2026, 7))
        popup.close()

        fallback_popup = CleanCalendarPopup(QDate())

        self.assertEqual(fallback_popup.current_date, QDate.currentDate())
        self.assertEqual(
            (fallback_popup.view_year, fallback_popup.view_month),
            (QDate.currentDate().year(), QDate.currentDate().month()),
        )
        fallback_popup.close()

    def test_navigation_wraps_across_year_boundaries(self):
        popup = CleanCalendarPopup(QDate(2026, 1, 10))

        popup.previous_month()
        self.assertEqual((popup.view_year, popup.view_month), (2025, 12))

        popup.next_month()
        self.assertEqual((popup.view_year, popup.view_month), (2026, 1))

        popup.view_month = 12
        popup.next_month()
        self.assertEqual((popup.view_year, popup.view_month), (2027, 1))
        popup.close()

    def test_choose_date_updates_selection_and_emits_date(self):
        popup = CleanCalendarPopup(QDate(2026, 7, 14))
        selected_spy = QSignalSpy(popup.date_selected)
        chosen_date = QDate(2026, 8, 3)

        popup.choose_date(chosen_date)

        self.assertEqual(popup.current_date, chosen_date)
        self.assertEqual(selected_spy.count(), 1)
        self.assertEqual(selected_spy.at(0), [chosen_date])
        popup.close()

    def test_compact_grid_has_fixed_non_overlapping_day_cells(self):
        popup = CleanCalendarPopup(QDate(2026, 7, 14))
        popup.show()
        self.application.processEvents()

        self.assertLessEqual(popup.width(), 330)
        self.assertLessEqual(popup.height(), 260)
        self.assertEqual(popup.grid.horizontalSpacing(), 4)
        self.assertEqual(popup.grid.verticalSpacing(), 4)

        day_buttons = [
            button
            for button in popup.findChildren(QToolButton)
            if button.objectName()
            in {"dayButton", "selectedDay", "outsideMonth"}
        ]

        self.assertTrue(day_buttons)

        for button in day_buttons:
            self.assertEqual(
                (button.width(), button.height()),
                (38, 28),
            )

        for row in range(1, popup.grid.rowCount()):
            for column in range(popup.grid.columnCount() - 1):
                left = popup.grid.itemAtPosition(row, column).widget()
                right = popup.grid.itemAtPosition(row, column + 1).widget()
                self.assertLess(left.geometry().right(), right.geometry().left())

        for row in range(1, popup.grid.rowCount() - 1):
            for column in range(popup.grid.columnCount()):
                upper = popup.grid.itemAtPosition(row, column).widget()
                lower = popup.grid.itemAtPosition(row + 1, column).widget()
                self.assertLess(upper.geometry().bottom(), lower.geometry().top())

        popup.close()

    def test_parent_button_styles_cannot_expand_or_overlap_calendar_cells(self):
        parent = QDialog()
        parent.setStyleSheet("""
            QPushButton {
                min-height: 44px;
                padding: 12px 20px;
            }

            QToolButton {
                background: transparent;
                border: none;
                padding: 0px;
            }
        """)
        parent.show()
        popup = CleanCalendarPopup(QDate(2026, 7, 14), parent=parent)
        popup.show()
        self.application.processEvents()

        self.assertLessEqual(popup.width(), 330)
        self.assertLessEqual(popup.height(), 260)

        for row in range(1, popup.grid.rowCount()):
            for column in range(popup.grid.columnCount() - 1):
                left = popup.grid.itemAtPosition(row, column).widget()
                right = popup.grid.itemAtPosition(row, column + 1).widget()
                self.assertLess(left.geometry().right(), right.geometry().left())

        for row in range(1, popup.grid.rowCount() - 1):
            for column in range(popup.grid.columnCount()):
                upper = popup.grid.itemAtPosition(row, column).widget()
                lower = popup.grid.itemAtPosition(row + 1, column).widget()
                self.assertLess(upper.geometry().bottom(), lower.geometry().top())

        popup.close()
        parent.close()

    def test_six_week_month_expands_popup_without_compressing_rows(self):
        popup = CleanCalendarPopup(QDate(2026, 7, 14))
        popup.show()
        self.application.processEvents()
        five_week_height = popup.height()

        popup.next_month()
        self.application.processEvents()

        self.assertEqual((popup.view_year, popup.view_month), (2026, 8))
        self.assertEqual(popup.grid.rowCount(), 7)
        self.assertGreater(popup.height(), five_week_height)
        self.assertLessEqual(popup.height(), 270)

        for row in range(1, popup.grid.rowCount() - 1):
            for column in range(popup.grid.columnCount()):
                upper = popup.grid.itemAtPosition(row, column).widget()
                lower = popup.grid.itemAtPosition(row + 1, column).widget()
                self.assertLess(upper.geometry().bottom(), lower.geometry().top())

        popup.close()


if __name__ == "__main__":
    unittest.main()
