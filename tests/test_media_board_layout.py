import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.media_board import MediaBoard
from app.watchlist_page import WatchlistPage


def make_media(media_id):
    return {
        "media_id": media_id,
        "metadata": {"title": f"Media {media_id}"},
        "posters": [],
    }


class FakeFilteredMedia:
    def __init__(self, count=0):
        self.media_list = [make_media(index) for index in range(count)]
        self.refresh_count = 0

    def refresh(self):
        self.refresh_count += 1
        return self.media_list


class MediaBoardLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.board = MediaBoard()
        self.board.resize(1000, 400)
        self.board.show()
        self.application.processEvents()

    def tearDown(self):
        self.board.close()
        self.application.processEvents()

    def test_all_filtered_media_are_rendered_in_a_top_aligned_grid(self):
        filtered_media = FakeFilteredMedia(12)

        self.board.load_media(filtered_media)
        self.application.processEvents()

        self.assertEqual(len(self.board.cards), 12)
        self.assertEqual(
            [card.get_current_media_key() for card in self.board.cards],
            list(range(12)),
        )
        self.assertEqual(self.board.posters_per_row, 5)
        self.assertEqual(self.board.row_count, 3)
        self.assertEqual(
            self.board.card_height,
            round(self.board.card_width * 1.5),
        )
        self.assertEqual(
            self.board.cards[10].geometry().left(),
            self.board.cards[0].geometry().left(),
        )
        self.assertEqual(
            self.board.cards[11].geometry().left(),
            self.board.cards[1].geometry().left(),
        )

    def test_empty_and_partial_results_create_no_placeholder_cards(self):
        for count in (0, 1, 4, 5, 6):
            with self.subTest(count=count):
                self.board.load_media(FakeFilteredMedia(count))
                self.application.processEvents()

                self.assertEqual(len(self.board.cards), count)
                self.assertEqual(
                    self.board.row_count,
                    0 if count == 0 else (count + 4) // 5,
                )
                self.assertEqual(
                    [
                        card.get_current_media_key()
                        for card in self.board.cards
                    ],
                    list(range(count)),
                )

    def test_density_reflow_reuses_cards_and_preserves_card_state(self):
        self.board.load_media(FakeFilteredMedia(12))
        self.application.processEvents()
        original_cards = list(self.board.cards)
        original_cards[4].on_pin_clicked()
        original_cards[6].poster_index = 2

        self.assertTrue(self.board.set_posters_per_row(3))
        self.application.processEvents()

        self.assertEqual(self.board.cards, original_cards)
        self.assertEqual(self.board.row_count, 4)
        self.assertTrue(self.board.cards[4].is_pinned)
        self.assertEqual(self.board.cards[6].poster_index, 2)

        self.assertTrue(self.board.set_posters_per_row(10))
        self.application.processEvents()

        self.assertEqual(self.board.cards, original_cards)
        self.assertEqual(self.board.row_count, 2)
        self.assertEqual(
            self.board.card_height,
            round(self.board.card_width * 1.5),
        )
        self.assertFalse(self.board.set_posters_per_row(10))

    def test_pin_keeps_its_logical_position_during_refresh(self):
        filtered_media = FakeFilteredMedia(8)
        self.board.load_media(filtered_media)
        pinned_card = self.board.cards[3]
        pinned_card.on_pin_clicked()

        filtered_media.media_list = list(
            reversed(filtered_media.media_list)
        )
        self.board.load_media(filtered_media)
        self.application.processEvents()

        self.assertIs(self.board.cards[3], pinned_card)
        self.assertEqual(pinned_card.get_current_media_key(), 3)
        self.assertTrue(pinned_card.is_pinned)
        self.assertEqual(
            len({
                card.get_current_media_key()
                for card in self.board.cards
            }),
            8,
        )

    def test_refresh_keeps_one_card_per_entry_even_with_duplicate_keys(self):
        filtered_media = FakeFilteredMedia(0)
        filtered_media.media_list = [
            make_media(1),
            make_media(1),
            make_media(2),
        ]
        self.board.load_media(filtered_media)
        self.board.cards[0].on_pin_clicked()

        self.board.load_media(filtered_media)
        self.application.processEvents()

        self.assertEqual(len(self.board.cards), 3)
        self.assertEqual(
            [card.get_current_media_key() for card in self.board.cards],
            [1, 1, 2],
        )

    def test_close_compacts_the_grid_and_refresh_restores_the_media(self):
        filtered_media = FakeFilteredMedia(7)
        self.board.load_media(filtered_media)
        dismissed_card = self.board.cards[2]
        dismissed_card.on_pin_clicked()

        dismissed_card.btn_close.click()
        self.application.processEvents()

        self.assertEqual(len(self.board.cards), 6)
        self.assertNotIn(dismissed_card, self.board.cards)
        self.assertFalse(dismissed_card.is_pinned)
        self.assertEqual(len(filtered_media.media_list), 7)

        self.board.load_media(filtered_media)
        self.application.processEvents()

        self.assertEqual(len(self.board.cards), 7)
        self.assertEqual(
            {card.get_current_media_key() for card in self.board.cards},
            set(range(7)),
        )

    def test_details_signal_still_forwards_after_multiple_reflows(self):
        media_draft = make_media(42)
        self.board.load_media(FakeFilteredMedia(1))
        self.board.cards[0].load_card_media(media_draft)
        spy = QSignalSpy(self.board.details_requested)

        self.board.set_posters_per_row(3)
        self.board.set_posters_per_row(10)
        self.board.cards[0].btn_info.click()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [media_draft])


class WatchlistScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.filtered_media = FakeFilteredMedia(20)
        self.filtered_media_patch = patch(
            "app.watchlist_page.FilteredMedia",
            return_value=self.filtered_media,
        )
        self.filtered_media_patch.start()
        self.page = WatchlistPage()
        self.page.resize(900, 500)
        self.page.show()
        self._process_layout_events()

    def tearDown(self):
        self.page.close()
        self.filtered_media_patch.stop()
        self.application.processEvents()

    def _process_layout_events(self):
        for _ in range(6):
            self.application.processEvents()

    def test_watchlist_scrolls_only_vertically(self):
        vertical_bar = self.page.scroll_area.verticalScrollBar()
        horizontal_bar = self.page.scroll_area.horizontalScrollBar()

        self.assertEqual(
            self.page.scroll_area.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertGreater(vertical_bar.maximum(), 0)
        self.assertEqual(horizontal_bar.maximum(), 0)

        dismissed_card = self.page.media_board.cards[0]
        dismissed_card.btn_close.click()
        self.application.processEvents()
        self.assertEqual(self.page.status_message, "20 filtered media")

    def test_reflow_keeps_the_anchor_card_at_the_same_vertical_offset(self):
        board = self.page.media_board
        scroll_bar = self.page.scroll_area.verticalScrollBar()
        anchor_card = board.cards[10]
        scroll_bar.setValue(anchor_card.geometry().top() + 17)
        self.application.processEvents()
        offset_before = scroll_bar.value() - anchor_card.geometry().top()

        self.page.set_posters_per_row(3)
        self._process_layout_events()

        self.assertIn(anchor_card, board.cards)
        self.assertEqual(
            scroll_bar.value() - anchor_card.geometry().top(),
            offset_before,
        )

    def test_horizontal_resize_changes_card_size_not_density(self):
        board = self.page.media_board
        original_width = board.card_width

        self.page.resize(1200, 500)
        self._process_layout_events()

        self.assertEqual(board.posters_per_row, 5)
        self.assertGreater(board.card_width, original_width)
        self.assertEqual(board.card_height, round(board.card_width * 1.5))
        self.assertEqual(
            self.page.scroll_area.horizontalScrollBar().maximum(),
            0,
        )

    def test_scrollbar_visibility_does_not_cause_resize_oscillation(self):
        self.page.resize(900, 1090)
        states = []

        for _ in range(16):
            self.application.processEvents()
            states.append((
                self.page.scroll_area.viewport().width(),
                self.page.scroll_area.verticalScrollBar().isVisibleTo(
                    self.page.scroll_area
                ),
                self.page.media_board.card_width,
                self.page.media_board.minimumHeight(),
            ))

        self.assertEqual(len(set(states[-8:])), 1)


if __name__ == "__main__":
    unittest.main()
