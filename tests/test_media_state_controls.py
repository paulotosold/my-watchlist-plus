import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app import media_details_dialog
from app.media_state_controls import (
    COLLECTION_PICK_OPTIONS,
    IMPRESSION_OPTIONS,
    ClickableEntryLabel,
    DownwardComboBox,
    populate_combo,
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

    def test_media_details_dialog_reexports_shared_controls(self):
        self.assertIs(
            media_details_dialog.ClickableEntryLabel,
            ClickableEntryLabel,
        )
        self.assertIs(
            media_details_dialog.IMPRESSION_OPTIONS,
            IMPRESSION_OPTIONS,
        )
        self.assertIs(
            media_details_dialog.COLLECTION_PICK_OPTIONS,
            COLLECTION_PICK_OPTIONS,
        )

    def test_populate_combo_selects_value_without_emitting_change(self):
        combo = DownwardComboBox()
        spy = QSignalSpy(combo.currentIndexChanged)

        populate_combo(combo, IMPRESSION_OPTIONS, "good")

        self.assertEqual(spy.count(), 0)
        self.assertEqual(combo.currentData(), "good")
        self.assertEqual(combo.currentText(), "👍 Good")
        combo.close()


if __name__ == "__main__":
    unittest.main()
