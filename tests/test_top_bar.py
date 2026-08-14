import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QToolButton

from app.ui.top_bar import TopBar
from app.watchlist.filtering import DEFAULT_FILTER_TEXT


class TopBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.top_bar = TopBar(default_filter_text=DEFAULT_FILTER_TEXT)
        self.top_bar.show()
        self.application.processEvents()

    def tearDown(self):
        self.top_bar.close()
        self.application.processEvents()

    def test_filter_input_contains_default_text_as_its_value(self):
        self.assertEqual(self.top_bar.filter_input.text(), DEFAULT_FILTER_TEXT)
        self.assertEqual(self.top_bar.filter_input.placeholderText(), "")

    def test_filter_enter_emits_the_exact_untrimmed_text(self):
        spy = QSignalSpy(self.top_bar.filter_submitted)

        QTest.keyClick(self.top_bar.filter_input, Qt.Key.Key_Return)
        self.top_bar.filter_input.setText(f" {DEFAULT_FILTER_TEXT}")
        QTest.keyClick(self.top_bar.filter_input, Qt.Key.Key_Return)

        self.assertEqual(spy.count(), 2)
        self.assertEqual(spy.at(0), [DEFAULT_FILTER_TEXT])
        self.assertEqual(spy.at(1), [f" {DEFAULT_FILTER_TEXT}"])

    def test_filter_controls_remain_configured_but_outside_the_layout(self):
        spy = QSignalSpy(self.top_bar.filter_submitted)
        layout = self.top_bar.layout()

        QTest.mouseClick(
            self.top_bar.filter_button,
            Qt.MouseButton.LeftButton,
        )

        self.assertEqual(spy.count(), 0)
        self.assertFalse(self.top_bar.filter_button.icon().isNull())
        for filter_widget in (
            self.top_bar.filter_label,
            self.top_bar.filter_input,
            self.top_bar.filter_button,
        ):
            with self.subTest(filter_widget=filter_widget):
                self.assertEqual(layout.indexOf(filter_widget), -1)

        self.assertGreaterEqual(
            layout.indexOf(self.top_bar.find_media_label),
            0,
        )
        self.assertGreaterEqual(
            layout.indexOf(self.top_bar.find_media_input),
            0,
        )
        self.assertTrue(self.top_bar.find_media_label.isVisible())
        self.assertTrue(self.top_bar.find_media_input.isVisible())
        direct_tool_buttons = [
            button
            for button in self.top_bar.findChildren(QToolButton)
            if button.parent() is self.top_bar
        ]
        self.assertEqual(direct_tool_buttons, [])

    def test_text_inputs_use_the_builtin_clear_button(self):
        for input_widget in (
            self.top_bar.filter_input,
            self.top_bar.find_media_input,
        ):
            with self.subTest(input_widget=input_widget):
                self.assertTrue(input_widget.isClearButtonEnabled())
                input_widget.setText("clear me")
                self.application.processEvents()
                clear_button = input_widget.findChild(QToolButton)

                self.assertIsNotNone(clear_button)
                self.assertEqual(
                    clear_button.isVisible(),
                    input_widget is self.top_bar.find_media_input,
                )
                clear_button.click()
                self.assertEqual(input_widget.text(), "")

    def test_find_media_enter_emits_the_trimmed_query(self):
        spy = QSignalSpy(self.top_bar.find_media_submitted)
        self.top_bar.find_media_input.setText("  tt1234567  ")

        QTest.keyClick(self.top_bar.find_media_input, Qt.Key.Key_Return)

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), ["tt1234567"])

    def test_labels_and_default_filter_text_are_configurable(self):
        history_bar = TopBar(
            filter_label_text="Filter History:",
            default_filter_text=(
                "All watch history entries, in chronological order"
            ),
            find_media_label_text="Open Media:",
            find_media_placeholder="Find one title",
        )

        try:
            self.assertEqual(history_bar.filter_label.text(), "Filter History:")
            self.assertEqual(
                history_bar.filter_input.text(),
                "All watch history entries, in chronological order",
            )
            self.assertEqual(history_bar.find_media_label.text(), "Open Media:")
            self.assertEqual(
                history_bar.find_media_input.placeholderText(),
                "Find one title",
            )
        finally:
            history_bar.close()


if __name__ == "__main__":
    unittest.main()
