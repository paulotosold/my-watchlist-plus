import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.watchlist_status_control import (
    SEGMENT_HORIZONTAL_PADDING,
    STATUS_LEFT_MARGIN,
    STATUS_RIGHT_MARGIN,
    WatchlistStatusControl,
)


class WatchlistStatusControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.control = WatchlistStatusControl()
        self.control.show()
        self.application.processEvents()

    def tearDown(self):
        self.control.close()
        self.application.processEvents()

    def test_composite_has_reload_segments_stretch_and_poster_size(self):
        layout = self.control.layout()

        self.assertFalse(self.control.reload_button.icon().isNull())
        self.assertEqual(
            self.control.reload_button.iconSize(),
            QSize(20, 20),
        )
        self.assertEqual(
            self.control.reload_button.size(),
            QSize(24, 24),
        )
        expected_filtered_width = (
            self.control.filtered_button.fontMetrics().horizontalAdvance(
                "9999 filtered titles"
            )
            + 2 * SEGMENT_HORIZONTAL_PADDING
        )
        expected_pinned_width = (
            self.control.pinned_button.fontMetrics().horizontalAdvance(
                "9999 pinned"
            )
            + 2 * SEGMENT_HORIZONTAL_PADDING
        )
        self.assertEqual(
            self.control.filtered_button.width(),
            expected_filtered_width,
        )
        self.assertEqual(
            self.control.pinned_button.width(),
            expected_pinned_width,
        )
        self.assertNotEqual(
            self.control.filtered_button.width(),
            self.control.pinned_button.width(),
        )
        self.assertGreater(layout.stretch(2), 0)
        self.assertEqual(
            layout.contentsMargins().left(),
            STATUS_LEFT_MARGIN,
        )
        self.assertEqual(
            layout.contentsMargins().right(),
            STATUS_RIGHT_MARGIN,
        )
        self.assertIsNotNone(self.control.poster_size_control)
        self.assertEqual(
            self.control.poster_size_control.title_label.text(),
            "Poster size",
        )

    def test_set_state_updates_counts_and_selection_without_emitting(self):
        scope_spy = QSignalSpy(self.control.pinned_only_requested)
        clear_spy = QSignalSpy(self.control.clear_all_pins_requested)
        segment_widths = (
            self.control.filtered_button.width(),
            self.control.pinned_button.width(),
        )

        self.control.set_state(42, 3, True)

        self.assertEqual(scope_spy.count(), 0)
        self.assertEqual(clear_spy.count(), 0)
        self.assertEqual(self.control.filtered_count, 42)
        self.assertEqual(self.control.pinned_count, 3)
        self.assertTrue(self.control.pinned_only)
        self.assertEqual(
            self.control.filtered_button.text(),
            "42 filtered titles",
        )
        self.assertEqual(self.control.pinned_button.text(), "3 pinned")
        self.assertFalse(self.control.filtered_button.isChecked())
        self.assertTrue(self.control.pinned_button.isChecked())
        self.assertTrue(self.control.pinned_button.isEnabled())
        self.assertTrue(self.control.clear_all_pins_action.isEnabled())

        self.control.set_state(999999, 999999, False)

        self.assertEqual(
            (
                self.control.filtered_button.width(),
                self.control.pinned_button.width(),
            ),
            segment_widths,
        )

        self.control.set_state(1, 0, True)

        self.assertEqual(scope_spy.count(), 0)
        self.assertEqual(
            self.control.filtered_button.text(),
            "1 filtered title",
        )
        self.assertEqual(self.control.pinned_button.text(), "0 pinned")
        self.assertFalse(self.control.pinned_only)
        self.assertTrue(self.control.filtered_button.isChecked())
        self.assertFalse(self.control.pinned_button.isEnabled())

    def test_segment_clicks_emit_the_requested_scope(self):
        spy = QSignalSpy(self.control.pinned_only_requested)
        self.control.set_state(10, 2, False)

        self.control.pinned_button.click()
        self.control.filtered_button.click()

        self.assertEqual(spy.count(), 2)
        self.assertEqual(spy.at(0), [True])
        self.assertEqual(spy.at(1), [False])
        self.assertTrue(self.control.filtered_button.isChecked())
        self.assertFalse(self.control.pinned_only)

    def test_clear_action_is_available_only_when_pins_exist(self):
        spy = QSignalSpy(self.control.clear_all_pins_requested)

        self.assertFalse(self.control.clear_all_pins_action.isEnabled())
        self.control.clear_all_pins_action.trigger()
        self.assertEqual(spy.count(), 0)

        self.control.set_state(10, 2, False)
        self.control.clear_all_pins_action.trigger()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(
            self.control.clear_all_pins_action.text(),
            "Clear all pinned",
        )

    def test_pinned_context_menu_opens_with_mouse_and_keyboard(self):
        self.control.set_state(10, 2, False)
        self.control.pinned_button.setFocus()
        menu_spy = QSignalSpy(
            self.control.pinned_context_menu.aboutToShow
        )

        local_position = QPoint(4, 4)
        context_event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            local_position,
            self.control.pinned_button.mapToGlobal(local_position),
        )
        self.application.sendEvent(
            self.control.pinned_button,
            context_event,
        )
        self.application.processEvents()
        self.assertEqual(menu_spy.count(), 1)
        self.control.pinned_context_menu.close()

        QTest.keyClick(
            self.control.pinned_button,
            Qt.Key.Key_Menu,
        )
        self.application.processEvents()
        self.assertEqual(menu_spy.count(), 2)
        self.control.pinned_context_menu.close()

        QTest.keyClick(
            self.control.pinned_button,
            Qt.Key.Key_F10,
            Qt.KeyboardModifier.ShiftModifier,
        )
        self.application.processEvents()
        self.assertEqual(menu_spy.count(), 3)
        self.control.pinned_context_menu.close()

    def test_reload_and_segments_are_keyboard_accessible(self):
        reload_spy = QSignalSpy(self.control.reload_requested)

        self.assertEqual(
            self.control.reload_button.focusPolicy(),
            Qt.FocusPolicy.StrongFocus,
        )
        self.assertFalse(self.control.reload_button.autoRaise())
        self.assertIn(
            "background: transparent",
            self.control.reload_button.styleSheet(),
        )
        self.assertEqual(
            self.control.filtered_button.focusPolicy(),
            Qt.FocusPolicy.StrongFocus,
        )
        self.assertTrue(self.control.reload_button.toolTip())
        self.assertTrue(self.control.filtered_button.toolTip())
        self.assertTrue(self.control.pinned_button.toolTip())

        self.control.reload_button.setFocus()
        QTest.keyClick(
            self.control.reload_button,
            Qt.Key.Key_Space,
        )

        self.assertEqual(reload_spy.count(), 1)


if __name__ == "__main__":
    unittest.main()
