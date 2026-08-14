import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QStyleOptionToolButton,
)

from app.ui.page_status_bar import PageStatusBar, STATUS_BAR_HEIGHT
from app.watchlist.status_control import (
    FILTERED_LABEL_MAX_TEXT,
    PINNED_BUTTON_MAX_TEXT,
    PINNED_CLEAR_BUTTON_SIZE,
    PINNED_CLEAR_ICON_SIZE,
    PINNED_CLEAR_CONTENT_TOP_PADDING,
    PINNED_PILL_ACTIVE_BACKGROUND,
    PINNED_PILL_HEIGHT,
    PINNED_PILL_INACTIVE_BACKGROUND,
    PINNED_PILL_RADIUS,
    PINNED_PILL_TEXT_COLOR,
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

    def test_composite_has_label_pill_stretch_and_poster_size(self):
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
        self.assertIn(
            "QToolButton:hover",
            self.control.reload_button.styleSheet(),
        )
        self.assertIn(
            "background: rgba(0, 0, 0, 18)",
            self.control.reload_button.styleSheet(),
        )
        self.assertIn(
            "border-radius: 12px",
            self.control.reload_button.styleSheet(),
        )
        self.assertIsInstance(self.control.filtered_label, QLabel)
        self.assertEqual(
            self.control.filtered_label.focusPolicy(),
            Qt.FocusPolicy.NoFocus,
        )
        expected_filtered_width = (
            self.control.filtered_label.fontMetrics().horizontalAdvance(
                FILTERED_LABEL_MAX_TEXT
            )
        )
        self.assertEqual(
            self.control.filtered_label.width(),
            expected_filtered_width,
        )
        self.assertEqual(
            self.control.pinned_pill.height(),
            PINNED_PILL_HEIGHT,
        )
        self.assertEqual(
            self.control.pinned_button.height(),
            PINNED_PILL_HEIGHT - 2,
        )
        self.assertEqual(
            self.control.clear_pins_button.size(),
            QSize(
                PINNED_CLEAR_BUTTON_SIZE,
                PINNED_CLEAR_BUTTON_SIZE,
            ),
        )
        self.assertEqual(self.control.clear_pins_button.text(), "")
        self.assertFalse(
            self.control.clear_pins_button.icon().isNull()
        )
        self.assertEqual(
            self.control.clear_pins_button.iconSize(),
            QSize(
                PINNED_CLEAR_ICON_SIZE,
                PINNED_CLEAR_ICON_SIZE,
            ),
        )
        self.assertGreaterEqual(
            self.control.pinned_button.width(),
            self.control.pinned_button.fontMetrics().horizontalAdvance(
                PINNED_BUTTON_MAX_TEXT
            ),
        )
        self.assertTrue(self.control.pinned_pill.isHidden())
        self.assertIn(
            f"border-radius: {PINNED_PILL_RADIUS}px",
            self.control.pinned_pill.styleSheet(),
        )
        self.assertIn(
            PINNED_PILL_INACTIVE_BACKGROUND,
            self.control.pinned_pill.styleSheet(),
        )
        self.assertIn(
            PINNED_PILL_ACTIVE_BACKGROUND,
            self.control.pinned_pill.styleSheet(),
        )
        self.assertIn(
            f"color: {PINNED_PILL_TEXT_COLOR}",
            self.control.pinned_pill.styleSheet(),
        )
        self.assertIn(
            f"padding-top: {PINNED_CLEAR_CONTENT_TOP_PADDING}px",
            self.control.pinned_pill.styleSheet(),
        )
        self.assertGreater(layout.stretch(3), 0)
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

        status_text_font = (
            self.control.poster_size_control.title_label.font()
        )
        for widget in (
            self.control.filtered_label,
            self.control.pinned_button,
            self.control.clear_pins_button,
        ):
            with self.subTest(widget=widget.objectName()):
                self.assertEqual(
                    widget.font().pointSizeF(),
                    status_text_font.pointSizeF(),
                )

    def test_status_bar_is_taller_than_its_reload_button(self):
        status_bar = PageStatusBar()
        control = WatchlistStatusControl(status_bar)
        status_bar.register_control("watchlist", control)
        status_bar.set_active_control("watchlist")
        control.set_state(10, 2, False)
        status_bar.show()
        self.application.processEvents()

        try:
            self.assertEqual(status_bar.height(), STATUS_BAR_HEIGHT)
            self.assertEqual(
                control.reload_button.height(),
                24,
            )
            self.assertEqual(
                STATUS_BAR_HEIGHT - PINNED_PILL_HEIGHT,
                4,
            )
            self.assertEqual(STATUS_BAR_HEIGHT % 2, 1)
            self.assertEqual(PINNED_PILL_HEIGHT % 2, 1)
            self.assertEqual(control.pinned_pill.y(), 2)
            self.assertEqual(
                control.height()
                - control.pinned_pill.geometry().bottom()
                - 1,
                2,
            )
            for button, top_padding in (
                (control.pinned_button, 0),
                (
                    control.clear_pins_button,
                    PINNED_CLEAR_CONTENT_TOP_PADDING,
                ),
            ):
                with self.subTest(button=button.objectName()):
                    self.assertGreaterEqual(
                        button.height()
                        - 2
                        - top_padding,
                        button.fontMetrics().height(),
                    )
            self.assertGreaterEqual(
                control.clear_pins_button.height()
                - 2
                - PINNED_CLEAR_CONTENT_TOP_PADDING,
                PINNED_CLEAR_ICON_SIZE,
            )
        finally:
            status_bar.close()
            self.application.processEvents()

    def test_set_state_updates_counts_visibility_without_emitting(self):
        scope_spy = QSignalSpy(self.control.pinned_only_requested)
        clear_spy = QSignalSpy(
            self.control.clear_all_pins_requested
        )
        filtered_width = self.control.filtered_label.width()

        self.control.set_state(42, 3, True)
        self.application.processEvents()

        self.assertEqual(scope_spy.count(), 0)
        self.assertEqual(clear_spy.count(), 0)
        self.assertEqual(self.control.filtered_count, 42)
        self.assertEqual(self.control.pinned_count, 3)
        self.assertTrue(self.control.pinned_only)
        self.assertEqual(
            self.control.filtered_label.text(),
            "42 titles – Showing: To Watch, Released, Random",
        )
        self.assertEqual(
            self.control.filtered_label.accessibleName(),
            "42 titles – Showing: To Watch, Released, Random",
        )
        self.assertEqual(self.control.pinned_button.text(), "3 pinned")
        self.assertFalse(self.control.pinned_pill.isHidden())
        self.assertTrue(self.control.pinned_button.isChecked())
        self.assertTrue(self.control.pinned_button.isEnabled())
        self.assertTrue(self.control.clear_pins_button.isEnabled())
        self.assertTrue(self.control.pinned_pill.property("active"))
        self.assertEqual(
            self.control.pinned_button.toolTip(),
            "Show all filtered media",
        )
        self.assertEqual(
            self.control.pinned_button.accessibleName(),
            "Show all filtered media",
        )

        pinned_button_width = self.control.pinned_button.width()
        pinned_pill_width = self.control.pinned_pill.width()
        self.control.set_state(999999, 999999, False)
        self.application.processEvents()

        self.assertEqual(
            self.control.filtered_label.width(),
            filtered_width,
        )
        self.assertEqual(
            self.control.pinned_button.width(),
            pinned_button_width,
        )
        self.assertEqual(
            self.control.pinned_pill.width(),
            pinned_pill_width,
        )
        self.assertFalse(self.control.pinned_pill.property("active"))

        self.control.set_state(1, 0, True)
        self.application.processEvents()

        self.assertEqual(scope_spy.count(), 0)
        self.assertEqual(
            self.control.filtered_label.text(),
            "1 title – Showing: To Watch, Released, Random",
        )
        self.assertEqual(self.control.pinned_button.text(), "0 pinned")
        self.assertFalse(self.control.pinned_only)
        self.assertFalse(self.control.pinned_button.isChecked())
        self.assertFalse(self.control.pinned_button.isEnabled())
        self.assertFalse(self.control.clear_pins_button.isEnabled())
        self.assertTrue(self.control.pinned_pill.isHidden())

    def test_pinned_button_toggles_scope_and_visual_state(self):
        spy = QSignalSpy(self.control.pinned_only_requested)
        self.control.set_state(10, 2, False)
        self.application.processEvents()

        expected_vertical_margin = (
            self.control.height() - PINNED_PILL_HEIGHT
        ) // 2
        self.assertEqual(
            self.control.pinned_pill.y(),
            expected_vertical_margin,
        )
        self.assertEqual(
            self.control.height()
            - self.control.pinned_pill.geometry().bottom()
            - 1,
            expected_vertical_margin,
        )
        self.assertFalse(self.control.pinned_pill.property("active"))
        self.assertEqual(
            self.control.pinned_button.toolTip(),
            "Show pinned media only",
        )
        self.assertEqual(
            self.control.pinned_button.accessibleName(),
            "Show pinned media only",
        )

        self.control.pinned_button.click()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [True])
        self.assertTrue(self.control.pinned_only)
        self.assertTrue(self.control.pinned_button.isChecked())
        self.assertTrue(self.control.pinned_pill.property("active"))
        self.assertEqual(
            self.control.pinned_button.toolTip(),
            "Show all filtered media",
        )
        self.assertEqual(
            self.control.pinned_button.accessibleName(),
            "Show all filtered media",
        )

        self.control.pinned_button.click()

        self.assertEqual(spy.count(), 2)
        self.assertEqual(spy.at(1), [False])
        self.assertFalse(self.control.pinned_only)
        self.assertFalse(self.control.pinned_button.isChecked())
        self.assertFalse(self.control.pinned_pill.property("active"))

    def test_pinned_controls_are_vertically_centered_in_the_pill(self):
        self.control.set_state(10, 2, False)
        self.application.processEvents()
        pill_center_y = self.control.pinned_pill.rect().center().y()

        self.assertEqual(
            self.control.pinned_button.geometry().center().y(),
            pill_center_y,
        )
        self.assertEqual(
            self.control.clear_pins_button.geometry().center().y(),
            pill_center_y,
        )

    def test_clear_button_is_independent_and_keyboard_accessible(self):
        scope_spy = QSignalSpy(self.control.pinned_only_requested)
        clear_spy = QSignalSpy(
            self.control.clear_all_pins_requested
        )

        self.assertFalse(self.control.clear_pins_button.isEnabled())
        self.control.clear_pins_button.click()
        self.assertEqual(clear_spy.count(), 0)

        self.control.set_state(10, 2, False)
        self.control.pinned_button.click()
        self.assertTrue(self.control.pinned_button.isChecked())
        scope_count = scope_spy.count()

        self.control.clear_pins_button.click()

        self.assertEqual(clear_spy.count(), 1)
        self.assertEqual(scope_spy.count(), scope_count)
        self.assertTrue(self.control.pinned_button.isChecked())

        self.control.clear_pins_button.setFocus()
        QTest.keyClick(
            self.control.clear_pins_button,
            Qt.Key.Key_Space,
        )

        self.assertEqual(clear_spy.count(), 2)
        self.assertEqual(scope_spy.count(), scope_count)
        self.assertTrue(self.control.pinned_button.isChecked())
        self.assertEqual(
            self.control.clear_pins_button.accessibleName(),
            "Clear all pinned",
        )
        self.assertEqual(
            self.control.clear_pins_button.toolTip(),
            "Clear all pinned",
        )

    def test_context_menu_controls_are_removed(self):
        self.assertFalse(hasattr(self.control, "pinned_context_menu"))
        self.assertFalse(hasattr(self.control, "clear_all_pins_action"))
        self.assertFalse(hasattr(self.control, "filtered_button"))

    def test_pill_text_stays_dark_with_a_dark_system_palette(self):
        original_palette = QPalette(self.application.palette())
        dark_palette = QPalette(original_palette)
        dark_palette.setColor(
            QPalette.ColorRole.ButtonText,
            QColor("#ffffff"),
        )

        try:
            self.application.setPalette(dark_palette)
            self.control.set_state(10, 2, False)
            self.application.processEvents()

            for button in (
                self.control.pinned_button,
                self.control.clear_pins_button,
            ):
                with self.subTest(button=button.objectName()):
                    option = QStyleOptionToolButton()
                    option.initFrom(button)
                    self.assertEqual(
                        option.palette.color(
                            QPalette.ColorRole.ButtonText
                        ).name(),
                        PINNED_PILL_TEXT_COLOR,
                    )
        finally:
            self.application.setPalette(original_palette)
            self.application.processEvents()

    def test_only_clear_button_changes_appearance_on_hover(self):
        style_sheet = self.control.pinned_pill.styleSheet()

        self.assertNotIn(
            "QToolButton#pinnedStatusButton:hover",
            style_sheet,
        )
        self.assertIn(
            "QToolButton#clearPinnedButton:hover",
            style_sheet,
        )

    def test_mouse_click_does_not_leave_status_actions_focused(self):
        reload_spy = QSignalSpy(self.control.reload_requested)
        scope_spy = QSignalSpy(
            self.control.pinned_only_requested
        )
        self.control.set_state(10, 2, False)
        self.control.poster_size_control.minus_button.setFocus()
        self.application.processEvents()

        QTest.mouseClick(
            self.control.reload_button,
            Qt.MouseButton.LeftButton,
        )
        self.application.processEvents()

        self.assertFalse(self.control.reload_button.hasFocus())
        self.assertEqual(reload_spy.count(), 1)

        self.control.reload_button.setFocus()
        self.application.processEvents()

        QTest.mouseClick(
            self.control.pinned_button,
            Qt.MouseButton.LeftButton,
        )
        self.application.processEvents()

        self.assertFalse(self.control.pinned_button.hasFocus())
        self.assertEqual(scope_spy.count(), 1)
        self.assertEqual(scope_spy.at(0), [True])

        self.control.reload_button.setFocus()
        QTest.keyClick(
            self.control.reload_button,
            Qt.Key.Key_Tab,
        )
        self.application.processEvents()

        self.assertTrue(self.control.pinned_button.hasFocus())
        QTest.keyClick(
            self.control.pinned_button,
            Qt.Key.Key_Space,
        )
        self.assertEqual(scope_spy.count(), 2)
        self.assertEqual(scope_spy.at(1), [False])

    def test_reload_and_pinned_controls_are_keyboard_accessible(self):
        reload_spy = QSignalSpy(self.control.reload_requested)
        scope_spy = QSignalSpy(self.control.pinned_only_requested)
        self.control.set_state(10, 2, False)

        self.assertEqual(
            self.control.reload_button.focusPolicy(),
            Qt.FocusPolicy.TabFocus,
        )
        self.assertFalse(self.control.reload_button.autoRaise())
        self.assertIn(
            "background: transparent",
            self.control.reload_button.styleSheet(),
        )
        self.assertEqual(
            self.control.pinned_button.focusPolicy(),
            Qt.FocusPolicy.TabFocus,
        )
        self.assertEqual(
            self.control.clear_pins_button.focusPolicy(),
            Qt.FocusPolicy.StrongFocus,
        )
        self.assertTrue(self.control.reload_button.toolTip())
        self.assertTrue(self.control.pinned_button.toolTip())
        self.assertTrue(self.control.clear_pins_button.toolTip())

        self.control.reload_button.setFocus()
        QTest.keyClick(
            self.control.reload_button,
            Qt.Key.Key_Space,
        )
        self.control.pinned_button.setFocus()
        QTest.keyClick(
            self.control.pinned_button,
            Qt.Key.Key_Space,
        )

        self.assertEqual(reload_spy.count(), 1)
        self.assertEqual(scope_spy.count(), 1)
        self.assertEqual(scope_spy.at(0), [True])


if __name__ == "__main__":
    unittest.main()
