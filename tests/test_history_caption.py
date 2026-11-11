import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.history.caption import HistoryCaption


def wheel(widget, *, pixel=QPoint(), angle=QPoint(), shift=False):
    point = widget.rect().center()
    event = QWheelEvent(
        QPointF(point), QPointF(widget.mapToGlobal(point)), pixel, angle,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    )
    QApplication.sendEvent(widget, event)
    return event


class HistoryCaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.caption = HistoryCaption()
        self.caption.resize(200, 24)
        self.caption.show()
        self.addCleanup(self.caption.close)
        self.application.processEvents()

    def settle(self):
        for _ in range(4):
            self.application.processEvents()

    def test_text_centers_then_scrolls_and_resets_when_it_fits_again(self):
        self.caption.set_text("Aug 2026 · S1:E1-5")
        self.settle()
        self.assertTrue(self.caption.label.alignment() & Qt.AlignmentFlag.AlignHCenter)
        self.caption.resize(60, 24)
        self.settle()
        bar = self.caption.horizontalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertTrue(self.caption.label.alignment() & Qt.AlignmentFlag.AlignLeft)
        self.assertFalse(bar.isVisible())
        bar.setValue(bar.maximum())
        self.caption.resize(80, 24)
        self.settle()
        self.assertLessEqual(bar.value(), bar.maximum())
        self.caption.resize(300, 24)
        self.settle()
        self.assertEqual(bar.value(), 0)
        self.assertEqual(bar.maximum(), 0)
        self.assertTrue(self.caption.label.alignment() & Qt.AlignmentFlag.AlignHCenter)

    def test_replacing_text_resets_offset_and_font_changes_recalculate(self):
        self.caption.resize(80, 24)
        self.caption.set_text("Aug 2026 · S1:E1-5, S2:E1-10")
        self.settle()
        bar = self.caption.horizontalScrollBar()
        bar.setValue(bar.maximum())
        self.caption.set_text("Sep 2026 · S1:E1-5, S2:E1-10")
        self.settle()
        self.assertEqual(bar.value(), 0)
        previous_maximum = bar.maximum()
        self.caption.label.setStyleSheet("font-size: 22px;")
        self.settle()
        self.assertGreater(bar.maximum(), previous_maximum)
        self.assertGreater(self.caption.caption_height(), 24)

    def test_approximate_date_captions_use_gray_until_replaced_by_an_explicit_date(self):
        label = self.caption.label
        role = label.foregroundRole()
        self.caption.set_text("Aug 2026")
        explicit_color = label.palette().color(role)

        for text in ("~Aug 2026 · S1:E1-5", "~unknown date"):
            self.caption.set_text(text)
            self.assertEqual(label.text(), text)
            self.assertEqual(label.palette().color(role), QColor("#666666"))

        self.caption.set_text("Sep 2026 · S1:E1-5")
        self.assertEqual(label.palette().color(role), explicit_color)

    def test_scrolling_reveals_the_complete_tail_with_its_right_margin(self):
        self.caption.resize(90, 24)
        self.caption.set_text("Sep 2026 · S1:E1-5, S2:E1-10")
        self.settle()
        viewport = self.caption.viewport()
        label = self.caption.label
        bar = self.caption.horizontalScrollBar()
        spy = QSignalSpy(self.caption.activated)

        for method in ("trackpad", "shift_wheel", "drag"):
            with self.subTest(method=method):
                bar.setValue(0)
                if method == "trackpad":
                    wheel(viewport, pixel=QPoint(-1000, 0))
                elif method == "shift_wheel":
                    wheel(viewport, angle=QPoint(0, -12000), shift=True)
                else:
                    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=QPoint(70, 12))
                    QTest.mouseMove(viewport, QPoint(-1000, 12))
                    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=QPoint(-1000, 12))
                self.settle()
                self.assertEqual(bar.value(), bar.maximum())
                # Reaching the scroll limit is insufficient if QLabel itself
                # clips its text. Its full styled size must fit in the content.
                self.assertGreaterEqual(label.width(), label.sizeHint().width())
                self.assertEqual(label.indent(), 0)
                visible_right = label.mapTo(viewport, label.contentsRect().topRight()).x()
                self.assertEqual(viewport.rect().right() - visible_right, 4)
        self.assertEqual(spy.count(), 0)

    def test_drag_scrolls_without_activating_and_click_and_keyboard_activate(self):
        self.caption.resize(120, 24)
        self.caption.set_text("Aug 2026 · S1:E1-5, S2:E1-10")
        self.settle()
        spy = QSignalSpy(self.caption.activated)
        viewport = self.caption.viewport()
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=QPoint(100, 12))
        QTest.mouseMove(viewport, QPoint(20, 12))
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=QPoint(20, 12))
        self.assertEqual(spy.count(), 0)
        self.assertGreater(self.caption.horizontalScrollBar().value(), 0)
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(30, 12))
        QTest.keyClick(self.caption, Qt.Key.Key_Return)
        QTest.keyClick(self.caption, Qt.Key.Key_Space)
        self.assertEqual(spy.count(), 3)
        self.assertTrue(self.caption.label.font().underline())

    def test_horizontal_and_shift_wheel_scroll_but_vertical_is_ignored(self):
        self.caption.resize(80, 24)
        self.caption.set_text("Aug 2026 · S1:E1-5, S2:E1-10")
        self.settle()
        bar = self.caption.horizontalScrollBar()
        wheel(self.caption.viewport(), pixel=QPoint(-20, 0))
        self.assertEqual(bar.value(), 20)
        wheel(self.caption.viewport(), angle=QPoint(0, -120), shift=True)
        self.assertEqual(bar.value(), 60)
        event = wheel(self.caption.viewport(), angle=QPoint(0, -120))
        self.assertEqual(bar.value(), 60)
        self.assertFalse(event.isAccepted())
