import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.watchlist.board import BOARD_BOTTOM_MARGIN, MediaBoard
from app.watchlist.page import WatchlistPage


def make_media(media_id):
    return {
        "media_id": media_id,
        "metadata": {"title": f"Media {media_id}"},
        "posters": [],
    }


class FakeFilteredMedia:
    def __init__(self, count=0):
        self.media_list = [make_media(index) for index in range(count)]
        self.next_media_list = None
        self.refresh_count = 0

    def refresh(self):
        self.refresh_count += 1

        if self.next_media_list is not None:
            self.media_list = list(self.next_media_list)
            self.next_media_list = None

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
        self.assertEqual(self.board.posters_per_row, 6)
        self.assertEqual(self.board.row_count, 2)
        self.assertEqual(
            self.board.card_height,
            round(self.board.card_width * 1.5),
        )
        self.assertEqual(
            self.board.cards[6].geometry().left(),
            self.board.cards[0].geometry().left(),
        )
        self.assertEqual(
            self.board.cards[7].geometry().left(),
            self.board.cards[1].geometry().left(),
        )

    def test_unused_width_is_split_evenly_around_the_grid(self):
        cases = (
            (2, 1000),
            (2, 1001),
            (5, 1001),
            (5, 1002),
            (8, 1006),
            (8, 1007),
        )

        for posters_per_row, width in cases:
            with self.subTest(
                posters_per_row=posters_per_row,
                width=width,
            ):
                self.board.resize(width, 400)
                self.board.set_posters_per_row(posters_per_row)
                self.board.load_media(
                    FakeFilteredMedia(posters_per_row + 2)
                )
                self.application.processEvents()

                first_card = self.board.cards[0]
                last_card_in_full_row = self.board.cards[
                    posters_per_row - 1
                ]
                left_gap = first_card.geometry().left()
                right_gap = (
                    self.board.rect().right()
                    - last_card_in_full_row.geometry().right()
                )
                spacing_width = (
                    posters_per_row - 1
                ) * self.board.grid_layout.horizontalSpacing()
                unused_width = (
                    self.board.width()
                    - posters_per_row * self.board.card_width
                    - spacing_width
                )

                self.assertEqual(self.board.width(), width)
                self.assertEqual(left_gap + right_gap, unused_width)
                self.assertLessEqual(abs(left_gap - right_gap), 1)
                self.assertEqual(
                    self.board.cards[
                        posters_per_row
                    ].geometry().left(),
                    first_card.geometry().left(),
                )

    def test_content_height_includes_space_after_the_last_row(self):
        self.board.load_media(FakeFilteredMedia(12))
        self.application.processEvents()

        last_card = self.board.cards[-1]
        self.assertEqual(
            self.board.minimumHeight() - 1
            - last_card.geometry().bottom(),
            BOARD_BOTTOM_MARGIN,
        )

    def test_empty_and_partial_results_create_no_placeholder_cards(self):
        for count in (0, 1, 4, 5, 6):
            with self.subTest(count=count):
                self.board.load_media(FakeFilteredMedia(count))
                self.application.processEvents()

                self.assertEqual(len(self.board.cards), count)
                self.assertEqual(
                    self.board.row_count,
                    0 if count == 0 else (count + 5) // 6,
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

        self.assertTrue(self.board.set_posters_per_row(2))
        self.application.processEvents()

        self.assertEqual(self.board.cards, original_cards)
        self.assertEqual(self.board.row_count, 6)
        self.assertTrue(self.board.cards[4].is_pinned)
        self.assertEqual(self.board.cards[6].poster_index, 2)

        self.assertTrue(self.board.set_posters_per_row(8))
        self.application.processEvents()

        self.assertEqual(self.board.cards, original_cards)
        self.assertEqual(self.board.row_count, 2)
        self.assertEqual(
            self.board.card_height,
            round(self.board.card_width * 1.5),
        )
        self.assertFalse(self.board.set_posters_per_row(8))

    def test_pinned_projection_restores_the_exact_canonical_grid(self):
        self.board.load_media(FakeFilteredMedia(12))
        self.application.processEvents()
        original_cards = list(self.board.cards)
        original_geometries = [
            card.geometry().getRect() for card in original_cards
        ]
        original_cards[2].poster_index = 4
        original_cards[2].on_pin_clicked()
        original_cards[8].on_pin_clicked()

        self.assertTrue(self.board.set_pinned_only(True))
        self.application.processEvents()

        self.assertEqual(self.board.cards, original_cards)
        self.assertEqual(
            self.board.visible_cards,
            [original_cards[2], original_cards[8]],
        )
        self.assertEqual(self.board.pinned_count, 2)
        self.assertTrue(self.board.pinned_only)
        self.assertEqual(self.board.row_count, 1)
        self.assertFalse(original_cards[2].isHidden())
        self.assertFalse(original_cards[8].isHidden())

        for card in original_cards:
            self.assertEqual(
                card.size().toTuple(),
                (self.board.card_width, self.board.card_height),
            )

            if card not in self.board.visible_cards:
                self.assertTrue(card.isHidden())

        self.assertTrue(self.board.set_pinned_only(False))
        self.application.processEvents()

        self.assertEqual(self.board.cards, original_cards)
        self.assertEqual(self.board.visible_cards, original_cards)
        self.assertEqual(
            [card.geometry().getRect() for card in original_cards],
            original_geometries,
        )
        self.assertEqual(original_cards[2].poster_index, 4)
        self.assertFalse(self.board.pinned_only)

    def test_view_state_signal_is_aggregated_once_per_operation(self):
        spy = QSignalSpy(self.board.view_state_changed)
        filtered_media = FakeFilteredMedia(6)

        self.board.load_media(filtered_media)
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [6, 0, False])

        pinned_card = self.board.cards[1]
        pinned_card.on_pin_clicked()
        self.assertEqual(spy.count(), 2)
        self.assertEqual(spy.at(1), [6, 1, False])

        self.assertTrue(self.board.set_pinned_only(True))
        self.assertEqual(spy.count(), 3)
        self.assertEqual(spy.at(2), [6, 1, True])

        pinned_card.on_pin_clicked()
        self.assertEqual(spy.count(), 4)
        self.assertEqual(spy.at(3), [6, 0, False])
        self.assertFalse(self.board.pinned_only)
        self.assertEqual(self.board.visible_cards, self.board.cards)

        self.assertFalse(self.board.set_pinned_only(True))
        self.assertFalse(self.board.clear_all_pins())
        self.assertEqual(spy.count(), 4)

        self.board.load_media(filtered_media)
        self.assertEqual(spy.count(), 5)
        self.assertEqual(spy.at(4), [6, 0, False])

        self.board.cards[0].on_pin_clicked()
        self.assertEqual(spy.count(), 6)

    def test_clear_all_pins_emits_once_and_returns_to_filtered(self):
        self.board.load_media(FakeFilteredMedia(9))
        self.board.cards[1].on_pin_clicked()
        self.board.cards[7].on_pin_clicked()
        self.board.set_pinned_only(True)
        spy = QSignalSpy(self.board.view_state_changed)

        self.assertTrue(self.board.clear_all_pins())
        self.application.processEvents()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [9, 0, False])
        self.assertFalse(self.board.pinned_only)
        self.assertEqual(self.board.pinned_count, 0)
        self.assertEqual(self.board.visible_cards, self.board.cards)
        self.assertTrue(all(not card.is_pinned for card in self.board.cards))

        self.assertFalse(self.board.clear_all_pins())
        self.assertEqual(spy.count(), 1)

    def test_unpin_and_dismiss_update_pinned_projection(self):
        self.board.load_media(FakeFilteredMedia(8))
        first_pinned = self.board.cards[1]
        second_pinned = self.board.cards[5]
        first_pinned.on_pin_clicked()
        second_pinned.on_pin_clicked()
        self.board.set_pinned_only(True)
        spy = QSignalSpy(self.board.view_state_changed)

        first_pinned.on_pin_clicked()
        self.application.processEvents()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [8, 1, True])
        self.assertTrue(first_pinned.isHidden())
        self.assertEqual(self.board.visible_cards, [second_pinned])
        self.assertEqual(
            second_pinned.geometry().left(),
            self.board.grid_layout.contentsMargins().left(),
        )

        second_pinned.btn_close.click()
        self.application.processEvents()

        self.assertEqual(spy.count(), 2)
        self.assertEqual(spy.at(1), [7, 0, False])
        self.assertFalse(self.board.pinned_only)
        self.assertNotIn(second_pinned, self.board.cards)
        self.assertEqual(self.board.visible_cards, self.board.cards)

    def test_refresh_reconciles_canonical_roster_while_pinned_only(self):
        filtered_media = FakeFilteredMedia(8)
        self.board.load_media(filtered_media)
        first_pinned = self.board.cards[2]
        second_pinned = self.board.cards[6]
        first_pinned.on_pin_clicked()
        second_pinned.on_pin_clicked()
        self.board.set_pinned_only(True)
        spy = QSignalSpy(self.board.view_state_changed)

        filtered_media.media_list = list(
            reversed(filtered_media.media_list)
        )
        self.board.load_media(filtered_media)
        self.application.processEvents()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [8, 2, True])
        self.assertIs(self.board.cards[2], first_pinned)
        self.assertIs(self.board.cards[6], second_pinned)
        self.assertEqual(
            self.board.visible_cards,
            [first_pinned, second_pinned],
        )

        filtered_media.media_list = [make_media(0), make_media(1)]
        self.board.load_media(filtered_media)
        self.application.processEvents()

        self.assertEqual(spy.count(), 2)
        self.assertEqual(spy.at(1), [2, 0, False])
        self.assertFalse(self.board.pinned_only)
        self.assertEqual(self.board.visible_cards, self.board.cards)

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

    def test_stable_reconcile_preserves_survivors_and_appends_only_new_media(self):
        filtered_media = FakeFilteredMedia(7)

        self.board.load_media(filtered_media)
        previous_media = list(filtered_media.media_list)
        cards_by_key = {
            card.get_current_media_key(): card
            for card in self.board.cards
        }
        dismissed_card = cards_by_key[2]
        surviving_card = cards_by_key[3]
        dismissed_card.btn_close.click()

        with tempfile.TemporaryDirectory() as directory:
            poster_path = Path(directory) / "poster.png"
            image = QImage(2, 3, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGray)
            self.assertTrue(image.save(str(poster_path)))
            posters = [
                {
                    "filename": f"poster-{index}.png",
                    "curation_status": "selected",
                }
                for index in range(3)
            ]
            surviving_media = make_media(3)
            surviving_media["posters"] = posters
            surviving_card._poster_path = lambda _filename: poster_path
            surviving_card.load_card_media(surviving_media)
            surviving_card.poster_index = 2
            surviving_card._save_current_poster_index()
            surviving_card.on_pin_clicked()
            self.board.set_pinned_only(True)

            filtered_media.media_list = [
                make_media(media_id)
                for media_id in (8, 7, 6, 5, 3, 2, 1, 0)
            ]
            filtered_media.media_list[4]["posters"] = posters
            self.board.reconcile_media(filtered_media, previous_media)

            self.assertEqual(surviving_card.poster_index, 2)

        self.assertEqual(
            [card.get_current_media_key() for card in self.board.cards],
            [0, 1, 3, 5, 6, 8, 7],
        )
        self.assertIs(self.board.cards[0], cards_by_key[0])
        self.assertIs(self.board.cards[1], cards_by_key[1])
        self.assertIs(self.board.cards[2], surviving_card)
        self.assertIs(self.board.cards[3], cards_by_key[5])
        self.assertIs(self.board.cards[4], cards_by_key[6])
        self.assertNotIn(dismissed_card, self.board.cards)
        self.assertNotIn(cards_by_key[4], self.board.cards)
        self.assertTrue(surviving_card.is_pinned)
        self.assertTrue(self.board.pinned_only)
        self.assertEqual(self.board.visible_cards, [surviving_card])

    def test_details_signal_still_forwards_after_multiple_reflows(self):
        media_draft = make_media(42)
        self.board.load_media(FakeFilteredMedia(1))
        self.board.cards[0].load_card_media(media_draft)
        spy = QSignalSpy(self.board.details_requested)

        self.board.set_posters_per_row(2)
        self.board.set_posters_per_row(8)
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
            "app.watchlist.page.FilteredMedia",
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
        board = self.page.media_board
        vertical_bar = self.page.scroll_area.verticalScrollBar()
        horizontal_bar = self.page.scroll_area.horizontalScrollBar()
        viewport = self.page.scroll_area.viewport()

        self.assertEqual(
            self.page.scroll_area.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            self.page.scroll_area.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertGreater(vertical_bar.maximum(), 0)
        self.assertFalse(vertical_bar.isVisible())
        self.assertEqual(horizontal_bar.maximum(), 0)
        self.assertEqual(board.width(), viewport.width())
        spacing = board.grid_layout.horizontalSpacing()
        expected_card_width = (
            viewport.width()
            - (board.posters_per_row - 1) * spacing
        ) // board.posters_per_row
        self.assertEqual(
            board.card_width,
            expected_card_width,
        )

        center = viewport.rect().center()
        wheel_event = QWheelEvent(
            QPointF(center),
            QPointF(viewport.mapToGlobal(center)),
            QPoint(),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        self.application.sendEvent(viewport, wheel_event)
        self.application.processEvents()
        self.assertGreater(vertical_bar.value(), 0)

        dismissed_card = self.page.media_board.cards[0]
        dismissed_card.btn_close.click()
        self.application.processEvents()
        self.assertEqual(self.page.status_message, "19 filtered titles")

    def test_reflow_keeps_the_anchor_card_at_the_same_vertical_offset(self):
        self.page.resize(900, 300)
        self._process_layout_events()
        board = self.page.media_board
        scroll_bar = self.page.scroll_area.verticalScrollBar()
        anchor_card = board.cards[12]
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

    def test_stable_refresh_restores_scroll_after_survivors_compact(self):
        self.page.resize(900, 300)
        self._process_layout_events()
        board = self.page.media_board
        scroll_bar = self.page.scroll_area.verticalScrollBar()
        anchor_card = board.cards[12]
        scroll_bar.setValue(anchor_card.geometry().top() + 17)
        self.application.processEvents()
        offset_before = scroll_bar.value() - anchor_card.geometry().top()
        self.filtered_media.next_media_list = [
            make_media(media_id)
            for media_id in range(1, 21)
        ]

        self.page.refresh_preserving_grid()
        self._process_layout_events()

        self.assertIn(anchor_card, board.cards)
        self.assertEqual(
            scroll_bar.value() - anchor_card.geometry().top(),
            offset_before,
        )
        self.assertEqual(
            [card.get_current_media_key() for card in board.cards],
            list(range(1, 21)),
        )

    def test_last_row_keeps_bottom_space_at_the_end_of_scroll(self):
        board = self.page.media_board
        scroll_bar = self.page.scroll_area.verticalScrollBar()
        viewport = self.page.scroll_area.viewport()
        scroll_bar.setValue(scroll_bar.maximum())
        self._process_layout_events()

        last_card = board.cards[-1]
        last_card_bottom = last_card.mapToGlobal(
            last_card.rect().bottomLeft()
        ).y()
        viewport_bottom = viewport.mapToGlobal(
            viewport.rect().bottomLeft()
        ).y()

        self.assertEqual(
            viewport_bottom - last_card_bottom,
            BOARD_BOTTOM_MARGIN,
        )

    def test_horizontal_resize_changes_card_size_not_density(self):
        board = self.page.media_board
        original_width = board.card_width

        self.page.resize(1200, 500)
        self._process_layout_events()

        self.assertEqual(board.posters_per_row, 6)
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
