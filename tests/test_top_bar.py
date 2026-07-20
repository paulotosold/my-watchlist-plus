import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QToolButton

from app.library_filter import DEFAULT_FILTER_TEXT
from app.top_bar import TopBar


class TopBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.top_bar = TopBar()
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

    def test_filter_button_is_inert_and_replaces_the_plus_button(self):
        spy = QSignalSpy(self.top_bar.filter_submitted)

        QTest.mouseClick(
            self.top_bar.filter_button,
            Qt.MouseButton.LeftButton,
        )

        self.assertEqual(spy.count(), 0)
        self.assertFalse(self.top_bar.filter_button.icon().isNull())
        self.assertEqual(len(self.top_bar.findChildren(QToolButton)), 1)

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
