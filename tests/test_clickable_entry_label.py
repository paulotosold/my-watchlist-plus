import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.media_state_controls import ClickableEntryLabel


class ClickableEntryLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.label = ClickableEntryLabel("Clickable entry")
        self.label.setFixedWidth(240)
        self.label.show()
        self.application.processEvents()
        self.label.clearFocus()

    def tearDown(self):
        self.label.close()
        self.application.processEvents()

    def test_only_clicks_on_rendered_text_activate(self):
        spy = QSignalSpy(self.label.activated)

        QTest.mouseClick(
            self.label,
            Qt.MouseButton.LeftButton,
            pos=self._text_point(),
        )
        QTest.mouseClick(
            self.label,
            Qt.MouseButton.LeftButton,
            pos=QPoint(self.label.width() - 2, self.label.height() // 2),
        )

        self.assertEqual(spy.count(), 1)

    def test_hover_and_focus_underline_text_and_hover_uses_pointer_cursor(self):
        QTest.mouseMove(self.label, self._text_point())
        self.application.processEvents()
        self.assertEqual(
            self.label.cursor().shape(),
            Qt.CursorShape.PointingHandCursor,
        )
        self.assertTrue(self.label.font().underline())

        QTest.mouseMove(
            self.label,
            QPoint(self.label.width() - 2, self.label.height() // 2),
        )
        self.application.processEvents()
        self.assertFalse(self.label.font().underline())

        self.label.setFocus(Qt.FocusReason.TabFocusReason)
        self.application.processEvents()
        self.assertTrue(self.label.font().underline())

    def test_enter_and_space_activate_focused_label(self):
        spy = QSignalSpy(self.label.activated)
        self.label.setFocus(Qt.FocusReason.TabFocusReason)

        QTest.keyClick(self.label, Qt.Key.Key_Return)
        QTest.keyClick(self.label, Qt.Key.Key_Space)

        self.assertEqual(spy.count(), 2)

    def test_dragging_to_select_text_does_not_activate(self):
        spy = QSignalSpy(self.label.activated)
        start = self._text_point()
        end = QPoint(
            min(self.label.width() - 1, start.x() + 70),
            start.y(),
        )

        QTest.mousePress(
            self.label,
            Qt.MouseButton.LeftButton,
            pos=start,
        )
        QTest.mouseMove(self.label, end, delay=10)
        QTest.mouseRelease(
            self.label,
            Qt.MouseButton.LeftButton,
            pos=end,
        )

        self.assertEqual(spy.count(), 0)
        self.assertTrue(self.label.hasSelectedText())

    def _text_point(self):
        return QPoint(2, self.label.height() // 2)


if __name__ == "__main__":
    unittest.main()
