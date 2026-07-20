import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.media_card import MediaCard


class MediaCardResizingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.card = MediaCard()
        self.card.show()
        self.application.processEvents()

    def tearDown(self):
        self.card.close()
        self.application.processEvents()

    def test_icons_scale_from_the_reference_width_with_usable_hitboxes(self):
        for width in (72, 269, 450):
            with self.subTest(width=width):
                self.card.setFixedSize(width, round(width * 1.5))
                self.application.processEvents()
                expected_square_icon = max(
                    1,
                    round(42 * width / 269),
                )
                expected_pin_width = max(
                    1,
                    round(140 * width / 269),
                )

                self.assertEqual(
                    self.card.btn_info.iconSize().toTuple(),
                    (expected_square_icon, expected_square_icon),
                )
                self.assertGreaterEqual(self.card.btn_info.width(), 24)
                self.assertGreaterEqual(self.card.btn_close.width(), 24)
                self.assertGreaterEqual(self.card.btn_pin.height(), 24)
                self.assertEqual(
                    self.card.btn_pin.iconSize().width(),
                    expected_pin_width,
                )
                self.assertGreaterEqual(self.card.btn_info.geometry().left(), 0)
                self.assertLessEqual(
                    self.card.btn_close.geometry().right(),
                    self.card.rect().right(),
                )
                self.assertLessEqual(
                    self.card.btn_pin.geometry().bottom(),
                    self.card.rect().bottom(),
                )
                self.assertLess(
                    self.card.btn_info.geometry().right(),
                    self.card.btn_close.geometry().left(),
                )

    def test_resizing_always_scales_from_the_original_poster(self):
        with tempfile.TemporaryDirectory() as directory:
            poster_path = Path(directory) / "poster.png"
            image = QImage(500, 750, QImage.Format.Format_RGB32)
            image.fill(0xFF336699)
            self.assertTrue(image.save(str(poster_path)))
            media_draft = {
                "media_id": 9,
                "metadata": {"title": "Poster test"},
                "posters": [{
                    "filename": poster_path.name,
                    "curation_status": "selected",
                    "is_default": True,
                }],
            }

            with (
                patch.object(
                    self.card,
                    "_poster_path",
                    return_value=poster_path,
                ),
                patch("app.media_card.random.randrange", return_value=0),
            ):
                self.card.init_card_session(
                    SimpleNamespace(media_list=[media_draft]),
                    media_draft,
                )

                for width in (269, 72, 450, 269):
                    self.card.setFixedSize(width, round(width * 1.5))
                    self.application.processEvents()
                    self.assertEqual(
                        self.card.poster_pixmap.size().toTuple(),
                        (500, 750),
                    )
                    self.assertEqual(
                        self.card.poster_layer.pixmap().size().toTuple(),
                        (width, round(width * 1.5)),
                    )

    def test_close_clears_pin_and_emits_one_dismiss_request(self):
        spy = QSignalSpy(self.card.dismiss_requested)
        self.card.is_disabled = False
        self.card.on_pin_clicked()

        self.card.btn_close.click()

        self.assertEqual(spy.count(), 1)
        self.assertFalse(self.card.is_pinned)
        self.assertFalse(hasattr(self.card, "btn_previous"))
        self.assertFalse(hasattr(self.card, "btn_next"))


if __name__ == "__main__":
    unittest.main()
