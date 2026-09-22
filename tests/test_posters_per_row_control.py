import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QComboBox, QStyle, QStyleOptionComboBox

from app.cabinet.board import POSTERS_PER_ROW_OPTIONS as CABINET_OPTIONS
from app.history.constants import HISTORY_POSTERS_PER_ROW_OPTIONS
from app.ui.posters_per_row_control import PostersPerRowControl
from app.watchlist.board import POSTERS_PER_ROW_OPTIONS


class PostersPerRowControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.control = PostersPerRowControl(value=6, options=POSTERS_PER_ROW_OPTIONS)
        self.control.show()
        self.application.processEvents()

    def tearDown(self):
        self.control.close()
        self.application.processEvents()

    def test_default_value_and_accessible_controls(self):
        self.assertEqual(self.control.posters_per_row, 6)
        self.assertEqual(self.control.title_label.text(), "Posters per row:")
        self.assertEqual(self.control.combo_box.currentText(), "6")
        self.assertFalse(self.control.combo_box.isEditable())
        self.assertEqual(self.control.combo_box.accessibleName(), "Posters per row")
        self.assertEqual(self.control.accessibleName(), "Posters per row: 6")
        self.assertEqual(self.control.combo_box.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        self.assertIs(self.control.title_label.buddy(), self.control.combo_box)

    def test_exact_options_for_each_page(self):
        for options, expected, default in (
            (POSTERS_PER_ROW_OPTIONS, [2, 3, 4, 5, 6, 7, 8, 9, 10], 6),
            (HISTORY_POSTERS_PER_ROW_OPTIONS, [4, 6, 8, 10, 12, 16, 24], 10),
            (CABINET_OPTIONS, [4, 6, 8, 10, 12, 16, 24], 10),
        ):
            with self.subTest(options=options):
                control = PostersPerRowControl(value=default, options=options)
                self.addCleanup(control.close)
                combo = control.combo_box
                self.assertEqual([combo.itemData(i) for i in range(combo.count())], expected)
                self.assertEqual([combo.itemText(i) for i in range(combo.count())], list(map(str, expected)))
                self.assertEqual(control.value(), default)
                self.assertEqual(control.minimum, expected[0])
                self.assertEqual(control.maximum, expected[-1])

    def test_selection_emits_once_per_change(self):
        spy = QSignalSpy(self.control.value_changed)
        self.control.combo_box.setCurrentText("10")
        self.control.combo_box.setCurrentText("2")
        self.control.combo_box.setCurrentText("2")
        self.assertEqual(self.control.posters_per_row, 2)
        self.assertEqual([spy.at(i)[0] for i in range(spy.count())], [10, 2])
        self.assertEqual(self.control.accessibleName(), "Posters per row: 2")

    def test_keyboard_selects_only_supported_options_and_stops_at_limits(self):
        control = PostersPerRowControl(value=12, options=HISTORY_POSTERS_PER_ROW_OPTIONS)
        control.show()
        self.addCleanup(control.close)
        combo = control.combo_box
        combo.setFocus()
        spy = QSignalSpy(control.value_changed)
        for key in (Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Down, Qt.Key.Key_Up):
            QTest.keyClick(combo, key)
        self.assertEqual([spy.at(i)[0] for i in range(spy.count())], [16, 24, 16])
        self.assertEqual(control.value(), 16)

    def test_focused_control_renders_without_highlight_before_and_after_selection(self):
        combo = self.control.combo_box
        combo.setFocus()
        self.application.processEvents()

        for expected in (6, 7):
            with self.subTest(value=expected):
                self.assertTrue(combo.hasFocus())
                self.assertEqual(combo.currentData(), expected)
                native = QStyleOptionComboBox()
                QComboBox.initStyleOption(combo, native)
                self.assertTrue(native.state & QStyle.StateFlag.State_HasFocus)

                painted = QStyleOptionComboBox()
                combo.initStyleOption(painted)
                self.assertFalse(painted.state & QStyle.StateFlag.State_HasFocus)
                self.assertFalse(painted.state & QStyle.StateFlag.State_Selected)
                self.assertTrue(painted.state & QStyle.StateFlag.State_Enabled)
                self.assertEqual(painted.currentText, str(expected))

                # Verify the actual paint path, with real focus still held.
                focused_image = combo.grab().toImage()
                combo.clearFocus()
                self.application.processEvents()
                self.assertEqual(focused_image, combo.grab().toImage())
                combo.setFocus()
                QTest.keyClick(combo, Qt.Key.Key_Down)

    def test_programmatic_values_snap_to_supported_options(self):
        control = PostersPerRowControl(value=10, options=HISTORY_POSTERS_PER_ROW_OPTIONS)
        self.addCleanup(control.close)
        spy = QSignalSpy(control.value_changed)
        for value in (100, 0, 11, 15, 16):
            control.set_value(value)
        self.assertEqual([spy.at(i)[0] for i in range(spy.count())], [24, 4, 10, 16])
        self.assertEqual(control.combo_box.currentText(), "16")

    def test_rejects_invalid_options(self):
        for options in ((), (6, 4), (4, 4, 6), (0, 4)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                PostersPerRowControl(value=6, options=options)


if __name__ == "__main__":
    unittest.main()
