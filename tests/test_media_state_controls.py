import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.paths import ASSETS_DIR
from app.ui.clickable_entry_label import ClickableEntryLabel
from app.ui.media_state_controls import (
    COLLECTION_PICK_OPTIONS,
    IMPRESSION_OPTIONS,
    MEDIA_STATE_COMBO_STYLE,
    STATUS_OPTIONS_BY_MEDIA_TYPE,
    DownwardComboBox,
    populate_combo,
    populate_status_combo,
)


class MediaStateControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_options_keep_the_existing_values_and_labels(self):
        self.assertEqual(
            IMPRESSION_OPTIONS,
            (
                (None, "None"),
                ("very_good", "👍👍 Very good"),
                ("good", "👍 Good"),
                ("meh", "😐 Meh"),
                ("not_for_me", "Not for me"),
                ("regret_watching", "😡 Waste of time"),
            ),
        )
        self.assertEqual(
            COLLECTION_PICK_OPTIONS,
            (
                (None, "None"),
                (True, "Yes!"),
                (False, "No"),
            ),
        )

    def test_combo_style_uses_cwd_independent_dropdown_path(self):
        dropdown_path = ASSETS_DIR / "dropdown_arrow.svg"

        self.assertTrue(dropdown_path.is_absolute())
        self.assertTrue(dropdown_path.is_file())
        self.assertIn(
            f'image: url("{dropdown_path.as_posix()}")',
            MEDIA_STATE_COMBO_STYLE,
        )
        self.assertNotIn("url(app/assets/", MEDIA_STATE_COMBO_STYLE)

    def test_populate_combo_selects_value_without_emitting_change(self):
        combo = DownwardComboBox()
        spy = QSignalSpy(combo.currentIndexChanged)

        populate_combo(combo, IMPRESSION_OPTIONS, "good")

        self.assertEqual(spy.count(), 0)
        self.assertEqual(combo.currentData(), "good")
        self.assertEqual(combo.currentText(), "👍 Good")
        combo.close()

    def test_status_options_match_media_type(self):
        movie_combo = DownwardComboBox()
        series_combo = DownwardComboBox()

        populate_status_combo(movie_combo, "movie", "watched")
        populate_status_combo(series_combo, "series", "dropped")

        self.assertEqual(movie_combo.currentText(), "Watched")
        self.assertEqual(movie_combo.findData("dropped"), -1)
        self.assertEqual(series_combo.currentText(), "Dropped")
        self.assertEqual(
            STATUS_OPTIONS_BY_MEDIA_TYPE["episode"][0],
            (None, "None"),
        )
        movie_combo.close()
        series_combo.close()


if __name__ == "__main__":
    unittest.main()
