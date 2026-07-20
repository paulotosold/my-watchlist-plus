import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.media_board import (
    DEFAULT_POSTERS_PER_ROW,
    MAX_POSTERS_PER_ROW,
    MIN_POSTERS_PER_ROW,
)
from app.posters_per_row_control import PostersPerRowControl


class PostersPerRowControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.control = PostersPerRowControl()
        self.control.show()
        self.application.processEvents()

    def tearDown(self):
        self.control.close()
        self.application.processEvents()

    def test_default_value_and_accessible_controls(self):
        self.assertEqual(
            self.control.posters_per_row,
            DEFAULT_POSTERS_PER_ROW,
        )
        self.assertEqual(self.control.title_label.text(), "Posters per row")
        self.assertEqual(
            self.control.decrease_button.text(),
            "\N{MINUS SIGN}",
        )
        self.assertEqual(self.control.value_label.text(), "5")
        self.assertEqual(self.control.increase_button.text(), "+")
        self.assertEqual(
            self.control.decrease_button.accessibleName(),
            "Decrease posters per row",
        )
        self.assertEqual(
            self.control.increase_button.accessibleName(),
            "Increase posters per row",
        )
        self.assertEqual(
            self.control.value_label.accessibleName(),
            "Current posters per row: 5",
        )
        self.assertEqual(
            self.control.decrease_button.focusPolicy(),
            Qt.FocusPolicy.StrongFocus,
        )
        self.assertTrue(self.control.decrease_button.toolTip())
        self.assertTrue(self.control.increase_button.toolTip())

    def test_buttons_clamp_at_limits_without_extra_emissions(self):
        spy = QSignalSpy(self.control.value_changed)

        for _ in range(10):
            self.control.decrease_button.click()

        self.assertEqual(
            self.control.posters_per_row,
            MIN_POSTERS_PER_ROW,
        )
        self.assertFalse(self.control.decrease_button.isEnabled())
        self.assertEqual(spy.count(), 2)

        for _ in range(10):
            self.control.increase_button.click()

        self.assertEqual(
            self.control.posters_per_row,
            MAX_POSTERS_PER_ROW,
        )
        self.assertFalse(self.control.increase_button.isEnabled())
        self.assertEqual(
            self.control.value_label.accessibleName(),
            "Current posters per row: 10",
        )
        self.assertEqual(
            [spy.at(index)[0] for index in range(spy.count())],
            [4, 3, 4, 5, 6, 7, 8, 9, 10],
        )

    def test_space_activates_the_focused_tool_button(self):
        spy = QSignalSpy(self.control.value_changed)
        self.control.increase_button.setFocus()

        QTest.keyClick(
            self.control.increase_button,
            Qt.Key.Key_Space,
        )

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [6])


if __name__ == "__main__":
    unittest.main()
