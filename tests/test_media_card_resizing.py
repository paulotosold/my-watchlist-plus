import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QImageReader
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.media_card import (
    MEDIA_CARD_BUTTON_MARGIN,
    MEDIA_CARD_ICON_HEIGHT,
    MediaCard,
    _icon_dimensions_for_height,
)


ICON_DIRECTORY = Path("app/assets/media_card_icons")


def expected_icon_size(filename):
    source_size = QImageReader(
        str(ICON_DIRECTORY / filename)
    ).size()

    if not source_size.isValid():
        raise AssertionError(f"Invalid test icon: {filename}")

    return (
        round(
            MEDIA_CARD_ICON_HEIGHT
            * source_size.width()
            / source_size.height()
        ),
        MEDIA_CARD_ICON_HEIGHT,
    )


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

    def test_icons_keep_fixed_sizes_and_margins_during_resizing(self):
        expected_info_size = expected_icon_size("info.png")
        expected_close_size = expected_icon_size("close.png")
        expected_pin_size = expected_icon_size("pin.png")
        expected_unpin_size = expected_icon_size("unpin.png")
        expected_pin_width = round(
            MEDIA_CARD_ICON_HEIGHT * 364 / 128
        )

        self.assertEqual(
            expected_info_size,
            (MEDIA_CARD_ICON_HEIGHT, MEDIA_CARD_ICON_HEIGHT),
        )
        self.assertEqual(
            expected_close_size,
            (MEDIA_CARD_ICON_HEIGHT, MEDIA_CARD_ICON_HEIGHT),
        )
        self.assertEqual(
            expected_pin_size,
            (expected_pin_width, MEDIA_CARD_ICON_HEIGHT),
        )
        self.assertEqual(
            expected_unpin_size,
            (expected_pin_width, MEDIA_CARD_ICON_HEIGHT),
        )

        for width in (72, 269, 450, 72):
            with self.subTest(width=width):
                height = round(width * 1.5)
                self.card.setFixedSize(width, height)
                self.application.processEvents()

                self.assertEqual(
                    self.card.btn_info.iconSize().toTuple(),
                    expected_info_size,
                )
                self.assertEqual(
                    self.card.btn_info.size().toTuple(),
                    expected_info_size,
                )
                self.assertEqual(
                    self.card.btn_close.iconSize().toTuple(),
                    expected_close_size,
                )
                self.assertEqual(
                    self.card.btn_close.size().toTuple(),
                    expected_close_size,
                )
                self.assertEqual(
                    self.card.btn_pin.iconSize().toTuple(),
                    expected_pin_size,
                )
                self.assertEqual(
                    self.card.btn_pin.size().toTuple(),
                    expected_pin_size,
                )
                self.assertEqual(
                    self.card.btn_info.x(),
                    MEDIA_CARD_BUTTON_MARGIN,
                )
                self.assertEqual(
                    self.card.btn_info.y(),
                    MEDIA_CARD_BUTTON_MARGIN,
                )
                self.assertEqual(
                    self.card.btn_close.y(),
                    MEDIA_CARD_BUTTON_MARGIN,
                )
                self.assertEqual(
                    width
                    - self.card.btn_close.x()
                    - self.card.btn_close.width(),
                    MEDIA_CARD_BUTTON_MARGIN,
                )
                self.assertEqual(
                    self.card.btn_pin.x(),
                    (width - self.card.btn_pin.width()) // 2,
                )
                self.assertEqual(
                    height
                    - self.card.btn_pin.y()
                    - self.card.btn_pin.height(),
                    MEDIA_CARD_BUTTON_MARGIN,
                )

    def test_pin_and_unpin_keep_the_same_size_and_geometry(self):
        self.card.setFixedSize(269, 404)
        self.application.processEvents()
        initial_size = self.card.btn_pin.size()
        initial_icon_size = self.card.btn_pin.iconSize()
        initial_geometry = self.card.btn_pin.geometry()

        self.card.on_pin_clicked()
        self.application.processEvents()

        self.assertTrue(self.card.is_pinned)
        self.assertEqual(self.card.btn_pin.size(), initial_size)
        self.assertEqual(self.card.btn_pin.iconSize(), initial_icon_size)
        self.assertEqual(self.card.btn_pin.geometry(), initial_geometry)

        self.card.on_pin_clicked()
        self.application.processEvents()

        self.assertFalse(self.card.is_pinned)
        self.assertEqual(self.card.btn_pin.size(), initial_size)
        self.assertEqual(self.card.btn_pin.iconSize(), initial_icon_size)
        self.assertEqual(self.card.btn_pin.geometry(), initial_geometry)

    def test_invalid_icon_dimensions_fall_back_to_a_square(self):
        self.assertEqual(
            _icon_dimensions_for_height(
                "app/assets/media_card_icons/missing.png",
                MEDIA_CARD_ICON_HEIGHT,
            ),
            (MEDIA_CARD_ICON_HEIGHT, MEDIA_CARD_ICON_HEIGHT),
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
