import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.media_board import MediaBoard
from app.media_card import MediaCard


class MediaDetailsRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_media_card_emits_a_copy_of_the_current_media(self):
        card = MediaCard()
        media_draft = {
            "media_id": 12,
            "metadata": {"title": "Test title"},
        }
        card.current_media = media_draft
        spy = QSignalSpy(card.details_requested)

        card.request_details()

        self.assertEqual(spy.count(), 1)
        emitted_draft = spy.at(0)[0]
        self.assertEqual(emitted_draft, media_draft)
        self.assertIsNot(emitted_draft, media_draft)
        card.close()

    def test_info_button_requests_details_without_opening_info_panel(self):
        card = MediaCard()
        media_draft = {
            "media_id": 12,
            "metadata": {"title": "Test title"},
        }
        card.current_media = media_draft
        spy = QSignalSpy(card.details_requested)

        card.btn_info.click()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [media_draft])
        self.assertFalse(card.info_panel.isVisible())
        card.close()

    def test_media_board_forwards_card_details_requests(self):
        media_draft = {"media_id": 18}
        filtered_media = SimpleNamespace(media_list=[media_draft])
        board = MediaBoard()
        board.load_media(filtered_media)
        spy = QSignalSpy(board.details_requested)

        board.cards[0].request_details()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [media_draft])
        board.close()


if __name__ == "__main__":
    unittest.main()
