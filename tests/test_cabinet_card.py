import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.cabinet.card import CabinetCard


class CabinetCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.poster_dir = Path(self.directory.name)
        for filename, color in (("first.png", "red"), ("default.png", "blue")):
            image = QImage(20, 30, QImage.Format.Format_RGB32)
            image.fill(QColor(color))
            self.assertTrue(image.save(str(self.poster_dir / filename)))
        self.card = CabinetCard()
        self.path_patch = patch.object(
            self.card,
            "_poster_path",
            side_effect=lambda filename: self.poster_dir / filename,
        )
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.card.close()
        self.card.deleteLater()
        self.directory.cleanup()
        self.application.processEvents()

    def test_default_poster_wins_and_cycling_is_circular(self):
        self.card.load_media(self._draft([
            self._poster("first.png", "selected", is_default=False),
            self._poster("default.png", "pending", is_default=True),
        ]))

        self.assertEqual(self.card.poster_filenames, ["default.png", "first.png"])
        self.assertEqual(self.card.poster_index, 0)
        self.card.on_overlay_clicked()
        self.assertEqual(self.card.poster_index, 1)
        self.assertEqual(
            self.card.poster_pixmap.toImage().pixelColor(0, 0),
            QColor("red"),
        )
        self.card.on_overlay_clicked()
        self.assertEqual(self.card.poster_index, 0)

    def test_falls_back_to_first_eligible_poster(self):
        self.card.load_media(self._draft([
            self._poster("ignored.png", "rejected", is_default=True),
            self._poster("first.png", "selected"),
            self._poster("default.png", "pending"),
        ]))

        self.assertEqual(self.card.poster_filenames, ["first.png", "default.png"])

    def test_info_emits_a_copy_and_watchlist_controls_are_absent(self):
        draft = self._draft([self._poster("first.png", "selected")])
        received = []
        self.card.details_requested.connect(received.append)
        self.card.load_media(draft)

        self.card.btn_info.click()

        self.assertEqual(received[0], draft)
        self.assertIsNot(received[0], self.card.current_media)
        self.assertFalse(hasattr(self.card, "btn_close"))
        self.assertFalse(hasattr(self.card, "btn_pin"))

    @staticmethod
    def _poster(filename, status, *, is_default=False):
        return {
            "filename": filename,
            "curation_status": status,
            "is_default": is_default,
        }

    @staticmethod
    def _draft(posters):
        return {
            "media_id": 1,
            "metadata": {"title": "Media"},
            "posters": posters,
            "user_data": {
                "is_cabinet_worthy": True,
                "cabinet_order": 1,
            },
        }


if __name__ == "__main__":
    unittest.main()
