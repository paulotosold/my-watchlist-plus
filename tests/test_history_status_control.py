import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.history.constants import (
    DEFAULT_HISTORY_POSTERS_PER_ROW,
    HISTORY_VIEW_GRID as GRID_VIEW,
    HISTORY_VIEW_LIST as LIST_VIEW,
    MAX_HISTORY_POSTERS_PER_ROW,
    MIN_HISTORY_POSTERS_PER_ROW,
)
from app.history.status_control import (
    ACTIVE_VIEW_BACKGROUND,
    ACTIVE_VIEW_BORDER,
    STATUS_LEFT_MARGIN,
    STATUS_RIGHT_MARGIN,
    HistoryStatusControl,
)


class HistoryStatusControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.control = HistoryStatusControl()
        self.control.show()
        self.application.processEvents()

    def tearDown(self):
        self.control.close()
        self.application.processEvents()

    def test_layout_places_count_left_and_view_controls_right(self):
        layout = self.control.layout()

        self.assertIs(
            layout.itemAt(0).widget(),
            self.control.count_label,
        )
        self.assertGreater(layout.stretch(1), 0)
        self.assertIs(
            layout.itemAt(2).widget(),
            self.control.poster_size_control,
        )
        self.assertIs(
            layout.itemAt(3).widget(),
            self.control.view_label,
        )
        self.assertIs(
            layout.itemAt(4).widget(),
            self.control.list_view_button,
        )
        self.assertIs(
            layout.itemAt(5).widget(),
            self.control.grid_view_button,
        )
        self.assertEqual(
            layout.contentsMargins().left(),
            STATUS_LEFT_MARGIN,
        )
        self.assertEqual(
            layout.contentsMargins().right(),
            STATUS_RIGHT_MARGIN,
        )
        self.assertEqual(self.control.view_label.text(), "View")

    def test_default_state_is_list_with_hidden_density_control(self):
        self.assertEqual(self.control.watched_count, 0)
        self.assertEqual(self.control.view_mode, LIST_VIEW)
        self.assertEqual(
            self.control.posters_per_row,
            DEFAULT_HISTORY_POSTERS_PER_ROW,
        )
        self.assertEqual(
            self.control.count_label.text(),
            "0 history entries – Showing: All, Newest First",
        )
        self.assertEqual(
            self.control.count_label.accessibleName(),
            "0 history entries – Showing: All, Newest First",
        )
        self.assertTrue(self.control.list_view_button.isChecked())
        self.assertFalse(self.control.grid_view_button.isChecked())
        self.assertTrue(
            self.control.poster_size_control.isHidden()
        )

    def test_view_buttons_have_icons_sizes_and_checked_style(self):
        self.assertTrue(self.control.view_button_group.exclusive())

        for button in (
            self.control.list_view_button,
            self.control.grid_view_button,
        ):
            with self.subTest(button=button.objectName()):
                self.assertTrue(button.isCheckable())
                self.assertFalse(button.icon().isNull())
                self.assertEqual(button.iconSize(), QSize(20, 20))
                self.assertEqual(button.size(), QSize(24, 24))
                self.assertTrue(
                    button.focusPolicy()
                    & Qt.FocusPolicy.ClickFocus
                )
                self.assertTrue(button.accessibleName())
                self.assertTrue(button.toolTip())
                self.assertIn(
                    ACTIVE_VIEW_BACKGROUND,
                    button.styleSheet(),
                )
                self.assertIn(
                    ACTIVE_VIEW_BORDER,
                    button.styleSheet(),
                )

    def test_set_state_updates_everything_without_emitting(self):
        view_spy = QSignalSpy(self.control.view_mode_requested)
        density_spy = QSignalSpy(
            self.control.posters_per_row_requested
        )
        internal_density_spy = QSignalSpy(
            self.control.poster_size_control.value_changed
        )

        self.control.set_state(1, GRID_VIEW, 24)
        self.application.processEvents()

        self.assertEqual(view_spy.count(), 0)
        self.assertEqual(density_spy.count(), 0)
        self.assertEqual(internal_density_spy.count(), 0)
        self.assertEqual(self.control.watched_count, 1)
        self.assertEqual(self.control.view_mode, GRID_VIEW)
        self.assertEqual(self.control.posters_per_row, 24)
        self.assertEqual(
            self.control.count_label.text(),
            "1 history entry – Showing: All, Newest First",
        )
        self.assertFalse(self.control.list_view_button.isChecked())
        self.assertTrue(self.control.grid_view_button.isChecked())
        self.assertFalse(
            self.control.poster_size_control.isHidden()
        )

        self.control.set_state(-10, LIST_VIEW, 3)
        self.application.processEvents()

        self.assertEqual(view_spy.count(), 0)
        self.assertEqual(density_spy.count(), 0)
        self.assertEqual(internal_density_spy.count(), 0)
        self.assertEqual(self.control.watched_count, 0)
        self.assertEqual(
            self.control.posters_per_row,
            MIN_HISTORY_POSTERS_PER_ROW,
        )
        self.assertEqual(
            self.control.count_label.text(),
            "0 history entries – Showing: All, Newest First",
        )
        self.assertTrue(
            self.control.poster_size_control.isHidden()
        )

    def test_clicking_view_buttons_emits_only_mode_changes(self):
        spy = QSignalSpy(self.control.view_mode_requested)

        self.control.list_view_button.click()
        self.assertEqual(spy.count(), 0)

        self.control.grid_view_button.click()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [GRID_VIEW])
        self.assertEqual(self.control.view_mode, GRID_VIEW)
        self.assertTrue(self.control.grid_view_button.isChecked())
        self.assertFalse(self.control.list_view_button.isChecked())
        self.assertFalse(
            self.control.poster_size_control.isHidden()
        )

        self.control.grid_view_button.click()
        self.assertEqual(spy.count(), 1)

        self.control.list_view_button.click()

        self.assertEqual(spy.count(), 2)
        self.assertEqual(spy.at(1), [LIST_VIEW])
        self.assertEqual(self.control.view_mode, LIST_VIEW)
        self.assertTrue(
            self.control.poster_size_control.isHidden()
        )

    def test_history_density_uses_6_to_24_limits(self):
        spy = QSignalSpy(
            self.control.posters_per_row_requested
        )
        self.control.set_state(
            10,
            GRID_VIEW,
            DEFAULT_HISTORY_POSTERS_PER_ROW,
        )

        self.control.poster_size_control.minus_button.click()
        self.control.poster_size_control.plus_button.click()

        self.assertEqual(self.control.posters_per_row, 18)
        self.assertEqual(
            [spy.at(index)[0] for index in range(spy.count())],
            [19, 18],
        )

        self.control.set_posters_per_row(
            MAX_HISTORY_POSTERS_PER_ROW
        )
        self.assertFalse(
            self.control.poster_size_control.minus_button.isEnabled()
        )
        self.control.set_posters_per_row(
            MIN_HISTORY_POSTERS_PER_ROW
        )
        self.assertFalse(
            self.control.poster_size_control.plus_button.isEnabled()
        )

    def test_view_buttons_are_keyboard_accessible(self):
        spy = QSignalSpy(self.control.view_mode_requested)
        self.control.grid_view_button.setFocus()

        QTest.keyClick(
            self.control.grid_view_button,
            Qt.Key.Key_Space,
        )

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [GRID_VIEW])
        self.assertTrue(self.control.grid_view_button.isChecked())

    def test_invalid_view_mode_is_rejected_without_changing_state(self):
        with self.assertRaisesRegex(
            ValueError,
            "Unsupported history view mode",
        ):
            self.control.set_state(10, "gallery", 18)

        self.assertEqual(self.control.view_mode, LIST_VIEW)
        self.assertEqual(
            self.control.count_label.text(),
            "0 history entries – Showing: All, Newest First",
        )


if __name__ == "__main__":
    unittest.main()
