import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QToolButton
from app.history.status_control import HistoryStatusControl


class HistoryStatusControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.control = HistoryStatusControl()
        self.control.show()
        self.addCleanup(self.control.close)

    def test_only_count_and_density_controls_remain(self):
        self.assertEqual(len(self.control.findChildren(QToolButton)), 2)
        self.assertEqual(self.control.posters_per_row, 10)
        self.assertFalse(self.control.poster_size_control.isHidden())
        self.assertFalse(hasattr(self.control, "view_mode_requested"))
        self.assertTrue(self.control.count_label.text().startswith("0 history entries"))

    def test_synchronizing_state_does_not_emit_requests(self):
        spy = QSignalSpy(self.control.posters_per_row_requested)
        self.control.set_state(1, 100)
        self.assertEqual(self.control.posters_per_row, 25)
        self.assertTrue(self.control.count_label.text().startswith("1 history entry –"))
        self.assertFalse(self.control.poster_size_control.minus_button.isEnabled())
        self.control.set_state(2, 0)
        self.assertEqual(self.control.posters_per_row, 6)
        self.assertFalse(self.control.poster_size_control.plus_button.isEnabled())
        self.assertEqual(spy.count(), 0)

    def test_size_buttons_use_correct_direction_and_limits(self):
        spy = QSignalSpy(self.control.posters_per_row_requested)
        self.control.poster_size_control.minus_button.click()
        self.assertEqual(spy.at(0), [11])
        self.control.poster_size_control.plus_button.click()
        self.assertEqual(spy.at(1), [10])
        self.control.set_posters_per_row(6)
        self.control.poster_size_control.plus_button.click()
        self.assertEqual(spy.count(), 2)
