import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from app.cabinet.board import (
    BOARD_HORIZONTAL_SPACING,
    BOARD_VERTICAL_SPACING,
    CabinetBoard,
)


class CabinetBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.board = CabinetBoard()
        self.board.resize(1000, 800)
        self.board.set_layout_width(1000)
        self.board.load_media([self._draft(index) for index in range(1, 11)])
        self.application.processEvents()

    def tearDown(self):
        self.board.close()
        self.board.deleteLater()
        self.application.processEvents()

    def test_density_limits_default_and_edge_to_edge_spacing(self):
        self.assertEqual(self.board.posters_per_row, 10)
        self.assertEqual(BOARD_HORIZONTAL_SPACING, 0)
        self.assertEqual(BOARD_VERTICAL_SPACING, 0)
        first, second = self.board.cards[:2]
        self.assertEqual(second.x() - first.geometry().right() - 1, BOARD_HORIZONTAL_SPACING)
        self.board.set_posters_per_row(4)
        fifth = self.board.cards[4]
        self.assertEqual(fifth.y() - first.geometry().bottom() - 1, BOARD_VERTICAL_SPACING)

        self.board.set_posters_per_row(1)
        self.assertEqual(self.board.posters_per_row, 4)
        self.board.set_posters_per_row(50)
        self.assertEqual(self.board.posters_per_row, 20)
        self.board.set_posters_per_row(10)
        self.assertEqual(self.board.posters_per_row, 10)

    def test_changing_columns_preserves_linear_sequence(self):
        original_ids = self.board.media_ids
        original_cards = list(self.board.cards)

        self.board.set_posters_per_row(4)
        self.board.set_posters_per_row(20)

        self.assertEqual(self.board.media_ids, original_ids)
        self.assertEqual(self.board.cards, original_cards)

    def test_slot_calculation_clamps_to_first_and_last(self):
        self.assertEqual(self.board.target_index_at(QPoint(-100, -100)), 0)
        self.assertEqual(self.board.target_index_at(QPoint(5000, 5000)), 9)
        self.assertEqual(
            self.board.target_index_at(self.board.slot_rects()[4].center()),
            4,
        )

    def test_preview_only_reflows_when_target_changes_and_cancel_restores(self):
        card = self.board.cards[1]
        original_ids = self.board.media_ids
        self._begin_preview(card)

        self.assertFalse(self.board.preview_reorder(card, 1))
        self.assertTrue(self.board.preview_reorder(card, 5))
        self.assertFalse(self.board.preview_reorder(card, 5))
        expected = list(original_ids)
        expected.insert(5, expected.pop(1))
        self.assertEqual(self.board.preview_media_ids, expected)

        QTest.qWait(180)
        self.board.cancel_drag()
        self.assertEqual(self.board.media_ids, original_ids)
        self.assertTrue(card.isVisible() or not self.board.isVisible())

    def test_preview_has_no_commit_and_valid_commit_emits_once(self):
        card = self.board.cards[0]
        original_ids = self.board.media_ids
        calls = []
        self._begin_preview(card)
        self.board.preview_reorder(card, 3)
        self.assertEqual(calls, [])

        def persist(expected, desired):
            calls.append((list(expected), list(desired)))
            self.board.confirm_reorder({
                "orders": {
                    media_id: len(desired) - index
                    for index, media_id in enumerate(desired)
                }
            })

        self.board.reorder_requested.connect(persist)
        self.assertTrue(self.board.commit_preview())

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], original_ids)
        self.assertEqual(self.board.media_ids, calls[0][1])
        self.assertEqual(
            [card.current_media["user_data"]["cabinet_order"] for card in self.board.cards],
            list(range(10, 0, -1)),
        )

    def test_failed_commit_restores_without_confirming(self):
        card = self.board.cards[2]
        original_ids = self.board.media_ids
        self._begin_preview(card)
        self.board.preview_reorder(card, 7)

        self.assertFalse(self.board.commit_preview())
        self.assertEqual(self.board.media_ids, original_ids)

    def test_auto_scroll_moves_near_the_viewport_bottom(self):
        scroll_area = QScrollArea()
        scroll_area.resize(500, 300)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.board)
        self.board.set_scroll_area(scroll_area)
        self.board.set_posters_per_row(4)
        scroll_area.show()
        self.application.processEvents()
        scroll_bar = scroll_area.verticalScrollBar()
        self.assertGreater(scroll_bar.maximum(), 0)
        scroll_bar.setValue(0)
        self.board._drag_card = self.board.cards[0]
        self.board._last_drag_global_position = scroll_area.viewport().mapToGlobal(
            scroll_area.viewport().rect().bottomLeft()
        )

        self.board._auto_scroll()

        self.assertGreater(scroll_bar.value(), 0)
        self.board._reset_drag_state()
        scroll_area.takeWidget()
        scroll_area.close()

    def _begin_preview(self, card):
        self.board._drag_card = card
        self.board._drag_original_cards = list(self.board.cards)
        self.board._preview_cards = list(self.board.cards)
        self.board._preview_index = self.board.cards.index(card)
        card.hide()

    @staticmethod
    def _draft(media_id):
        return {
            "media_id": media_id,
            "metadata": {"title": f"Media {media_id}"},
            "posters": [],
            "user_data": {
                "is_cabinet_worthy": True,
                "cabinet_order": 11 - media_id,
            },
        }


if __name__ == "__main__":
    unittest.main()
