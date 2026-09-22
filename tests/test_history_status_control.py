import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QComboBox, QToolButton
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
        self.assertEqual(len(self.control.findChildren(QToolButton)), 0)
        self.assertEqual(self.control.posters_per_row, 10)
        self.assertFalse(self.control.poster_size_control.isHidden())
        self.assertFalse(hasattr(self.control, "view_mode_requested"))
        self.assertTrue(self.control.count_label.text().startswith("0 history entries"))

    def test_synchronizing_state_does_not_emit_requests(self):
        spy = QSignalSpy(self.control.posters_per_row_requested)
        self.control.set_state(1, 100)
        self.assertEqual(self.control.posters_per_row, 24)
        self.assertTrue(self.control.count_label.text().startswith("1 history entry –"))
        self.assertEqual(self.control.poster_size_control.combo_box.currentText(), "24")
        self.control.set_state(2, 0)
        self.assertEqual(self.control.posters_per_row, 4)
        self.assertEqual(self.control.poster_size_control.combo_box.currentText(), "4")
        self.assertEqual(spy.count(), 0)

    def test_dropdown_requests_supported_densities(self):
        spy = QSignalSpy(self.control.posters_per_row_requested)
        combo = self.control.poster_size_control.combo_box
        self.assertEqual(len(self.control.findChildren(QComboBox)), 1)
        combo.setCurrentText("16")
        self.assertEqual(spy.at(0), [16])
        combo.setCurrentText("24")
        self.assertEqual(spy.at(1), [24])
        self.control.set_posters_per_row(4)
        combo.setCurrentText("4")
        self.assertEqual(spy.count(), 2)
