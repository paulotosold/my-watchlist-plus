import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Signal
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QWidget

from app.watchlist.board import DEFAULT_POSTERS_PER_ROW
from app.watchlist.filtering import DEFAULT_FILTER_TEXT
from app.watchlist.page import WatchlistPage


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
    view_state_changed = Signal(int, int, bool)

    def __init__(
        self,
        posters_per_row=DEFAULT_POSTERS_PER_ROW,
        parent=None,
    ):
        super().__init__(parent)
        self.posters_per_row = posters_per_row
        self.cards = []
        self.visible_cards = []
        self.pinned_count = 0
        self.pinned_only = False
        self.loaded_media = []
        self.reconciled_media = []
        self.reflow_count = 0
        self.layout_width = None
        self.scroll_area = None
        self.reset_order_values = []

    def load_media(self, filtered_media, *, reset_order=False):
        self.loaded_media.append(filtered_media)
        self.reset_order_values.append(reset_order)
        target_count = len(filtered_media.media_list)
        cards = list(self.cards[:target_count])

        while len(cards) < target_count:
            cards.append(FakeCard(parent=self))

        self.set_cards(cards)
        self._emit_view_state()

    def reconcile_media(self, filtered_media, previously_filtered_media):
        self.reconciled_media.append((
            filtered_media,
            list(previously_filtered_media),
        ))
        self.load_media(filtered_media)

    def set_posters_per_row(self, value):
        if value == self.posters_per_row:
            return False

        self.posters_per_row = value
        return True

    def set_layout_width(self, value):
        self.layout_width = value
        return True

    def set_scroll_area(self, scroll_area):
        self.scroll_area = scroll_area

    def reflow_cards(self):
        self.reflow_count += 1

    def set_pinned_only(self, pinned_only):
        pinned_only = bool(pinned_only)

        if pinned_only == self.pinned_only:
            return False

        if pinned_only and self.pinned_count == 0:
            return False

        self.pinned_only = pinned_only
        self._sync_visible_cards()
        self._emit_view_state()
        return True

    def clear_all_pins(self):
        if self.pinned_count == 0:
            return False

        for card in self.cards:
            card.is_pinned = False

        self.pinned_count = 0
        self.pinned_only = False
        self._sync_visible_cards()
        self._emit_view_state()
        return True

    def set_cards(self, cards):
        self.cards = list(cards)
        self.pinned_count = sum(card.is_pinned for card in self.cards)
        self._sync_visible_cards()

    def _sync_visible_cards(self):
        self.visible_cards = [
            card
            for card in self.cards
            if not self.pinned_only or card.is_pinned
        ]

        for index, card in enumerate(self.visible_cards):
            card.setGeometry(0, index * 120, 100, 100)

        content_height = (
            len(self.visible_cards) * 120
            if self.visible_cards
            else 0
        )
        self.setMinimumHeight(content_height)
        self.updateGeometry()

    def _emit_view_state(self):
        self.view_state_changed.emit(
            len(self.cards),
            self.pinned_count,
            self.pinned_only,
        )


class FakeCard(QWidget):
    def __init__(self, *, is_pinned=False, parent=None):
        super().__init__(parent)
        self.is_pinned = is_pinned


class WatchlistPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeFilteredMedia.instances = []
        self.filtered_media_patch = patch(
            "app.watchlist.page.FilteredMedia",
            FakeFilteredMedia,
        )
        self.media_board_patch = patch(
            "app.watchlist.page.MediaBoard",
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

    def _process_events(self):
        for _ in range(4):
            self.application.processEvents()

    def _install_cards(self, count, pinned_indexes=()):
        pinned_indexes = set(pinned_indexes)
        cards = [
            FakeCard(
                is_pinned=index in pinned_indexes,
                parent=self.page.media_board,
            )
            for index in range(count)
        ]
        self.page.media_board.set_cards(cards)
        self.page.media_board._emit_view_state()
        self.page.resize(500, 320)
        self.page.show()
        self._process_events()
        return cards

    def test_watchlist_is_eagerly_loaded_with_default_status(self):
        self.assertTrue(self.page.is_loaded)
        self.assertFalse(self.page.is_invalidated)
        self.assertEqual(self.page.filtered_media.refresh_count, 1)
        self.assertEqual(
            self.page.media_board.loaded_media,
            [self.page.filtered_media],
        )
        self.assertEqual(
            self.page.status_message,
            "2 titles – Showing: To Watch, Released, Random",
        )
        self.assertEqual(
            self.page.top_bar.filter_input.text(),
            DEFAULT_FILTER_TEXT,
        )
        self.assertEqual(
            self.page.posters_per_row,
            DEFAULT_POSTERS_PER_ROW,
        )
        self.assertEqual(self.page.filtered_count, 2)
        self.assertEqual(self.page.pinned_count, 0)
        self.assertFalse(self.page.pinned_only)

    def test_board_view_state_is_relayed_with_title_grammar(self):
        state_spy = QSignalSpy(self.page.watchlist_state_changed)
        status_spy = QSignalSpy(self.page.status_message_changed)
        card = FakeCard(is_pinned=True, parent=self.page.media_board)
        self.page.media_board.set_cards([card])

        self.page.media_board._emit_view_state()

        self.assertEqual(state_spy.at(0), [1, 1, False])
        self.assertEqual(
            status_spy.at(0),
            ["1 title – Showing: To Watch, Released, Random"],
        )
        self.assertEqual(
            self.page.status_message,
            "1 title – Showing: To Watch, Released, Random",
        )
        self.assertEqual(self.page.filtered_count, 1)
        self.assertEqual(self.page.pinned_count, 1)

    def test_posters_per_row_is_forwarded_to_the_board(self):
        self.assertTrue(self.page.set_posters_per_row(7))
        self.assertEqual(self.page.media_board.posters_per_row, 7)
        self.assertFalse(self.page.set_posters_per_row(7))

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
        self.assertEqual(
            self.page.media_board.reconciled_media,
            [(current_filtered_media, current_filtered_media.media_list)],
        )

    def test_generic_refresh_preserves_pinned_only_mode(self):
        cards = self.page.media_board.cards
        cards[0].is_pinned = True
        self.page.media_board.set_cards(cards)
        self.assertTrue(self.page.set_pinned_only(True))

        self.page.refresh_media_view()

        self.assertTrue(self.page.pinned_only)
        self.assertEqual(self.page.pinned_count, 1)
        self.assertIs(
            self.page.media_board.loaded_media[-1],
            self.page.filtered_media,
        )
        self.assertEqual(
            self.page.media_board.reset_order_values[-1],
            False,
        )

    def test_automatic_refresh_reconciles_against_previous_filter_roster(self):
        previous_media = list(self.page.filtered_media.media_list)
        current_filtered_media = self.page.filtered_media

        result = self.page.refresh_preserving_grid()

        self.assertEqual(current_filtered_media.refresh_count, 2)
        self.assertEqual(result, current_filtered_media.media_list)
        self.assertEqual(
            self.page.media_board.reconciled_media,
            [(current_filtered_media, previous_media)],
        )
        self.assertFalse(self.page.is_invalidated)

    def test_exact_default_filter_replaces_the_filtered_media(self):
        original_filtered_media = self.page.filtered_media
        status_spy = QSignalSpy(self.page.status_message_changed)

        self.page.on_filter_input(DEFAULT_FILTER_TEXT)

        self.assertIsNot(self.page.filtered_media, original_filtered_media)
        self.assertEqual(self.page.filtered_media.refresh_count, 1)
        self.assertEqual(status_spy.count(), 1)
        self.assertEqual(
            status_spy.at(0),
            ["2 titles – Showing: To Watch, Released, Random"],
        )

    def test_default_filter_reload_forces_filtered_mode(self):
        cards = self.page.media_board.cards
        cards[0].is_pinned = True
        self.page.media_board.set_cards(cards)
        self.assertTrue(self.page.set_pinned_only(True))
        original_filtered_media = self.page.filtered_media

        self.page.on_filter_input(DEFAULT_FILTER_TEXT)

        self.assertFalse(self.page.pinned_only)
        self.assertIsNot(self.page.filtered_media, original_filtered_media)
        self.assertEqual(
            self.page.status_message,
            "2 titles – Showing: To Watch, Released, Random",
        )
        self.assertTrue(self.page.media_board.reset_order_values[-1])

    def test_pinned_only_rejects_zero_pins_without_storing_an_anchor(self):
        self.assertFalse(self.page.set_pinned_only(True))
        self.assertFalse(self.page.pinned_only)
        self.assertIsNone(self.page._filtered_scroll_anchor)

    def test_pinned_view_starts_at_top_and_restores_surviving_card(self):
        cards = self._install_cards(8, pinned_indexes=(1, 6))
        scroll_bar = self.page.scroll_area.verticalScrollBar()
        scroll_bar.setValue(cards[4].geometry().top() + 17)

        self.assertTrue(self.page.set_pinned_only(True))
        self.assertEqual(scroll_bar.value(), 0)
        self.assertTrue(self.page.set_pinned_only(False))
        self._process_events()

        self.assertEqual(
            scroll_bar.value(),
            cards[4].geometry().top() + 17,
        )

    def test_filtered_anchor_falls_back_to_surviving_neighbor(self):
        cards = self._install_cards(8, pinned_indexes=(1, 6))
        scroll_bar = self.page.scroll_area.verticalScrollBar()
        removed_anchor = cards[4]
        scroll_bar.setValue(removed_anchor.geometry().top() + 11)
        self.assertTrue(self.page.set_pinned_only(True))

        remaining_cards = [
            card for card in cards if card is not removed_anchor
        ]
        self.page.media_board.set_cards(remaining_cards)
        expected_neighbor = remaining_cards[4]

        self.assertTrue(self.page.set_pinned_only(False))
        self._process_events()

        self.assertEqual(
            scroll_bar.value(),
            expected_neighbor.geometry().top() + 11,
        )

    def test_resize_anchor_uses_visible_cards(self):
        cards = self._install_cards(5, pinned_indexes=(3,))
        hidden_card = cards[0]
        visible_card = cards[3]
        self.page.media_board.pinned_only = True
        self.page.media_board._sync_visible_cards()
        hidden_card.setGeometry(0, 0, 100, 100)
        visible_card.setGeometry(0, 120, 100, 100)
        self.page.media_board.setMinimumHeight(1000)
        self.page.media_board.updateGeometry()
        self._process_events()
        self.page.scroll_area.verticalScrollBar().setValue(50)

        anchor = self.page._capture_scroll_anchor()

        self.assertIs(anchor[0], visible_card)
        self.assertEqual(anchor[1], -70)

    def test_clear_all_auto_return_restores_filtered_anchor(self):
        cards = self._install_cards(8, pinned_indexes=(1, 6))
        scroll_bar = self.page.scroll_area.verticalScrollBar()
        scroll_bar.setValue(cards[4].geometry().top() + 9)
        self.assertTrue(self.page.set_pinned_only(True))

        self.assertTrue(self.page.clear_all_pins())
        self._process_events()

        self.assertFalse(self.page.pinned_only)
        self.assertEqual(self.page.pinned_count, 0)
        self.assertEqual(
            scroll_bar.value(),
            cards[4].geometry().top() + 9,
        )

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

    def test_find_media_query_can_be_cleared_through_the_page(self):
        self.page.top_bar.find_media_input.setText("Arrival")

        self.page.clear_find_media_query()

        self.assertEqual(self.page.top_bar.find_media_input.text(), "")


if __name__ == "__main__":
    unittest.main()
