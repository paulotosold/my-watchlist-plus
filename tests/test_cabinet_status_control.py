import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.cabinet.status_control import CabinetStatusControl


class CabinetStatusControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.control = CabinetStatusControl()

    def tearDown(self):
        self.control.close()
        self.control.deleteLater()
        self.application.processEvents()

    def test_has_exact_count_text_density_and_no_refresh(self):
        self.assertEqual(
            self.control.count_label.text(),
            "0 titles – Showing: Cabinet Worthy, Custom Order",
        )
        self.assertEqual(self.control.poster_size_control.posters_per_row, 10)
        self.assertEqual(self.control.poster_size_control.minimum, 4)
        self.assertEqual(self.control.poster_size_control.maximum, 20)
        self.assertFalse(hasattr(self.control, "reload_button"))

        self.control.set_state(1, 12)
        self.assertEqual(
            self.control.count_label.text(),
            "1 title – Showing: Cabinet Worthy, Custom Order",
        )
        self.assertEqual(self.control.poster_size_control.posters_per_row, 12)

    def test_density_request_is_independent_and_clamped(self):
        received = []
        self.control.posters_per_row_requested.connect(received.append)

        self.control.poster_size_control.set_value(100)
        self.control.poster_size_control.set_value(1)

        self.assertEqual(received, [20, 4])


if __name__ == "__main__":
    unittest.main()
