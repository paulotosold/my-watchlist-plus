import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.cabinet.page import CabinetPage


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class CabinetPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.drafts = [self._draft(1, 2), self._draft(2, 1)]
        self.connection = FakeConnection()
        self.connection_patch = patch(
            "app.cabinet.page.get_connection",
            return_value=self.connection,
        )
        self.load_patch = patch(
            "app.cabinet.page.initialize_and_load_cabinet",
            return_value=self.drafts,
        )
        self.get_connection = self.connection_patch.start()
        self.initialize_and_load = self.load_patch.start()
        self.page = CabinetPage()

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.load_patch.stop()
        self.connection_patch.stop()
        self.application.processEvents()

    def test_is_lazy_and_ensure_loaded_initializes_once_until_invalidated(self):
        self.assertFalse(self.page.is_loaded)
        self.assertTrue(self.page.is_invalidated)
        self.initialize_and_load.assert_not_called()

        loaded = self.page.ensure_loaded()
        self.assertEqual(loaded, self.drafts)
        self.initialize_and_load.assert_called_once_with(self.connection)
        self.page.ensure_loaded()
        self.assertEqual(self.initialize_and_load.call_count, 1)

        self.page.invalidate()
        self.page.ensure_loaded()
        self.assertEqual(self.initialize_and_load.call_count, 2)

    def test_top_bar_only_exposes_find_and_details_are_forwarded(self):
        self.page.show()
        self.application.processEvents()
        self.assertTrue(self.page.top_bar.find_media_input.isVisible())
        self.assertFalse(self.page.top_bar.filter_input.isVisible())

        find_queries = []
        detail_drafts = []
        self.page.find_media_requested.connect(find_queries.append)
        self.page.details_requested.connect(detail_drafts.append)
        self.page.ensure_loaded()
        self.page.top_bar.find_media_input.setText("tt1234567")
        self.page.top_bar.find_media_input.returnPressed.emit()
        self.page.media_board.cards[0].btn_info.click()

        self.assertEqual(find_queries, ["tt1234567"])
        self.assertEqual(detail_drafts[0]["media_id"], 1)

    def test_density_preserves_linear_order(self):
        self.page.ensure_loaded()
        cards = list(self.page.media_board.cards)

        self.assertTrue(self.page.set_posters_per_row(4))
        self.assertEqual(self.page.media_board.cards, cards)
        self.assertEqual(self.page.media_board.media_ids, [1, 2])

    def test_reorder_is_persisted_once_then_confirmed_in_memory(self):
        self.page.ensure_loaded()
        board = self.page.media_board
        card = board.cards[0]
        board._drag_card = card
        board._drag_original_cards = list(board.cards)
        board._preview_cards = list(board.cards)
        board._preview_index = 0
        board.preview_reorder(card, 1)
        result = {
            "media_ids": [2, 1],
            "orders": {2: 2, 1: 1},
            "updated_count": 2,
        }

        with patch(
            "app.cabinet.page.persist_cabinet_reorder",
            return_value=result,
        ) as persist:
            self.assertTrue(board.commit_preview())

        persist.assert_called_once_with(self.connection, [1, 2], [2, 1])
        self.assertEqual(board.media_ids, [2, 1])

    @staticmethod
    def _draft(media_id, cabinet_order):
        return {
            "media_id": media_id,
            "metadata": {"title": f"Media {media_id}"},
            "posters": [],
            "user_data": {
                "is_cabinet_worthy": True,
                "cabinet_order": cabinet_order,
            },
        }


if __name__ == "__main__":
    unittest.main()
