import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Signal
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QWidget

from app.library_filter import DEFAULT_FILTER_TEXT
from app.watchlist_page import WatchlistPage


class FakeFilteredMedia:
    instances = []

    def __init__(self):
        self.media_list = [{"media_id": 1}, {"media_id": 2}]
        self.next_media_index = 0
        self.refresh_count = 0
        self.instances.append(self)

    def refresh(self):
        self.refresh_count += 1
        return self.media_list


class FakeMediaBoard(QWidget):
    details_requested = Signal(object)

    def __init__(self, rows, columns, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.loaded_media = []

    def load_media(self, filtered_media):
        self.loaded_media.append(filtered_media)


class WatchlistPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeFilteredMedia.instances = []
        self.filtered_media_patch = patch(
            "app.watchlist_page.FilteredMedia",
            FakeFilteredMedia,
        )
        self.media_board_patch = patch(
            "app.watchlist_page.MediaBoard",
            FakeMediaBoard,
        )
        self.filtered_media_patch.start()
        self.media_board_patch.start()
        self.page = WatchlistPage()

    def tearDown(self):
        self.page.close()
        self.media_board_patch.stop()
        self.filtered_media_patch.stop()
        self.application.processEvents()

    def test_watchlist_is_eagerly_loaded_with_default_status(self):
        self.assertTrue(self.page.is_loaded)
        self.assertFalse(self.page.is_invalidated)
        self.assertEqual(self.page.filtered_media.refresh_count, 1)
        self.assertEqual(
            self.page.media_board.loaded_media,
            [self.page.filtered_media],
        )
        self.assertEqual(self.page.status_message, "2 filtered media")
        self.assertEqual(
            self.page.top_bar.filter_input.text(),
            DEFAULT_FILTER_TEXT,
        )

    def test_invalidate_defers_refresh_until_ensure_loaded(self):
        current_filtered_media = self.page.filtered_media

        self.page.invalidate()

        self.assertTrue(self.page.is_invalidated)
        self.assertEqual(current_filtered_media.refresh_count, 1)

        self.page.ensure_loaded()

        self.assertFalse(self.page.is_invalidated)
        self.assertEqual(current_filtered_media.refresh_count, 2)
        self.assertEqual(
            self.page.media_board.loaded_media,
            [current_filtered_media, current_filtered_media],
        )

    def test_exact_default_filter_replaces_the_filtered_media(self):
        original_filtered_media = self.page.filtered_media
        status_spy = QSignalSpy(self.page.status_message_changed)

        self.page.on_filter_input(DEFAULT_FILTER_TEXT)

        self.assertIsNot(self.page.filtered_media, original_filtered_media)
        self.assertEqual(self.page.filtered_media.refresh_count, 1)
        self.assertEqual(status_spy.count(), 1)
        self.assertEqual(status_spy.at(0), ["2 filtered media"])

    def test_non_default_filter_is_only_printed(self):
        current_filtered_media = self.page.filtered_media

        with patch("builtins.print") as print_mock:
            self.page.on_filter_input("movies directed by Jane Campion")

        print_mock.assert_called_once_with(
            "Filter Library:",
            "movies directed by Jane Campion",
        )
        self.assertIs(self.page.filtered_media, current_filtered_media)
        self.assertEqual(current_filtered_media.refresh_count, 1)

    def test_find_and_details_requests_are_forwarded(self):
        find_spy = QSignalSpy(self.page.find_media_requested)
        details_spy = QSignalSpy(self.page.details_requested)
        media_draft = {"media_id": 42}

        self.page.top_bar.find_media_submitted.emit("tt1234567")
        self.page.media_board.details_requested.emit(media_draft)

        self.assertEqual(find_spy.at(0), ["tt1234567"])
        self.assertEqual(details_spy.at(0), [media_draft])


if __name__ == "__main__":
    unittest.main()
