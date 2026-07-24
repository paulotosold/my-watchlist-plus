import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt
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
        self.assertEqual(self.control.title_label.text(), "Poster size")
        self.assertFalse(hasattr(self.control, "value_label"))
        self.assertFalse(self.control.minus_button.icon().isNull())
        self.assertFalse(self.control.plus_button.icon().isNull())
        self.assertEqual(
            self.control.minus_button.iconSize(),
            QSize(20, 20),
        )
        self.assertEqual(
            self.control.minus_button.size(),
            QSize(24, 24),
        )
        self.assertFalse(self.control.minus_button.autoRaise())
        self.assertIn(
            "background: transparent",
            self.control.minus_button.styleSheet(),
        )
        self.assertIn(
            "QToolButton:disabled",
            self.control.minus_button.styleSheet(),
        )
        self.assertEqual(
            self.control.minus_button.accessibleName(),
            "Decrease poster size",
        )
        self.assertEqual(
            self.control.plus_button.accessibleName(),
            "Increase poster size",
        )
        self.assertEqual(
            self.control.accessibleName(),
            "Poster size: 5 posters per row",
        )
        self.assertEqual(
            self.control.minus_button.focusPolicy(),
            Qt.FocusPolicy.StrongFocus,
        )
        self.assertTrue(self.control.minus_button.toolTip())
        self.assertTrue(self.control.plus_button.toolTip())

    def test_minus_makes_posters_smaller_and_plus_makes_them_larger(self):
        spy = QSignalSpy(self.control.value_changed)

        self.control.minus_button.click()
        self.control.plus_button.click()

        self.assertEqual(self.control.posters_per_row, 5)
        self.assertEqual(
            [spy.at(index)[0] for index in range(spy.count())],
            [6, 5],
        )

    def test_buttons_clamp_at_limits_without_extra_emissions(self):
        spy = QSignalSpy(self.control.value_changed)

        for _ in range(10):
            self.control.minus_button.click()

        self.assertEqual(
            self.control.posters_per_row,
            MAX_POSTERS_PER_ROW,
        )
        self.assertFalse(self.control.minus_button.isEnabled())
        self.assertEqual(spy.count(), 3)

        for _ in range(10):
            self.control.plus_button.click()

        self.assertEqual(
            self.control.posters_per_row,
            MIN_POSTERS_PER_ROW,
        )
        self.assertFalse(self.control.plus_button.isEnabled())
        self.assertEqual(
            self.control.accessibleName(),
            "Poster size: 2 posters per row",
        )
        self.assertEqual(
            [spy.at(index)[0] for index in range(spy.count())],
            [6, 7, 8, 7, 6, 5, 4, 3, 2],
        )

    def test_space_activates_the_focused_tool_button(self):
        spy = QSignalSpy(self.control.value_changed)
        self.control.minus_button.setFocus()

        QTest.keyClick(
            self.control.minus_button,
            Qt.Key.Key_Space,
        )

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [6])


if __name__ == "__main__":
    unittest.main()
