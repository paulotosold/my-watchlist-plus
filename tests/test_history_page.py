import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QStackedWidget

from app.history.page import HistoryPage
from app.history.repository import HISTORY_DEFAULT_FILTER_TEXT
from test_history_caption import wheel
from test_history_grid import make_entry
from test_history_page_views import FakeConnection


class HistoryPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.entries = [make_entry(1), make_entry(2)]
        connection = patch("app.history.page.get_connection", side_effect=FakeConnection)
        loader = patch("app.history.page.load_default_history_entries", side_effect=lambda conn: self.entries)
        connection.start()
        self.loader = loader.start()
        self.addCleanup(connection.stop)
        self.addCleanup(loader.stop)
        self.page = HistoryPage()
        self.addCleanup(self.page.close)

    def test_only_grid_loads_lazily_and_refresh_reuses_cards(self):
        self.assertEqual(self.page.grid_board.tiles, [])
        self.assertEqual(self.page.findChildren(QStackedWidget), [])
        self.assertFalse(hasattr(self.page, "set_view_mode"))
        self.page.ensure_loaded()
        tiles = list(self.page.grid_board.tiles)
        self.page.ensure_loaded()
        self.assertEqual(self.loader.call_count, 1)
        self.page.invalidate()
        self.page.ensure_loaded()
        self.assertEqual(self.loader.call_count, 2)
        self.assertEqual(self.page.grid_board.tiles, tiles)
        self.assertEqual(self.page.status_message, "2 history entries – Showing: All Time, Newest First")

    def test_separate_poster_and_entry_requests(self):
        self.page.ensure_loaded()
        poster = QSignalSpy(self.page.details_requested)
        caption = QSignalSpy(self.page.watch_entry_details_requested)
        self.page.grid_board.tiles[0].poster_label.request_details()
        self.page.grid_board.tiles[1].caption.activated.emit()
        self.assertEqual(poster.count(), 1)
        self.assertEqual(poster.at(0), [1])
        self.assertEqual(caption.count(), 1)
        self.assertEqual(caption.at(0), [2, 2])

    def test_density_is_clamped_and_notifies_only_changes(self):
        spy = QSignalSpy(self.page.density_changed)
        self.assertEqual(self.page.posters_per_row, 10)
        self.assertFalse(self.page.set_posters_per_row(10))
        self.page.set_posters_per_row(0)
        self.assertEqual(self.page.posters_per_row, 6)
        self.page.set_posters_per_row(100)
        self.assertEqual(self.page.posters_per_row, 25)
        self.assertEqual([spy.at(i) for i in range(spy.count())], [[6], [25]])

    def test_filter_and_search_preserve_existing_semantics(self):
        self.page.ensure_loaded()
        with patch("builtins.print") as output:
            self.page.on_filter_input("something else")
            output.assert_called_once()
        self.assertEqual(self.loader.call_count, 1)
        self.page.on_filter_input(HISTORY_DEFAULT_FILTER_TEXT)
        self.assertEqual(self.loader.call_count, 2)
        self.page.top_bar.find_media_input.setText("query")
        self.page.clear_find_media_query()
        self.assertEqual(self.page.top_bar.find_media_input.text(), "")

    def test_vertical_wheel_over_caption_scrolls_history(self):
        self.entries[:] = [make_entry(index) for index in range(200)]
        self.page.resize(1000, 400)
        self.page.show()
        self.page.ensure_loaded()
        for _ in range(8):
            self.application.processEvents()
        bar = self.page.grid_scroll_area.verticalScrollBar()
        self.assertEqual(bar.value(), 0)
        caption = self.page.grid_board.tiles[0].caption
        wheel(caption.viewport(), angle=QPoint(0, -120))
        self.application.processEvents()
        delta = bar.value()
        self.assertGreater(delta, 0)
        bar.setValue(0)
        wheel(self.page.grid_scroll_area.viewport(), angle=QPoint(0, -120))
        self.assertEqual(bar.value(), delta)
        bar.setValue(0)
        wheel(caption.viewport(), pixel=QPoint(1, -30), angle=QPoint(0, -120))
        self.assertGreater(bar.value(), 0)
        self.assertEqual(caption.horizontalScrollBar().value(), 0)

    def test_empty_and_single_entry_counts(self):
        self.entries.clear()
        self.page.ensure_loaded()
        self.assertTrue(self.page.status_message.startswith("0 history entries"))
        self.entries.append(make_entry(1))
        self.page.refresh_history()
        self.assertTrue(self.page.status_message.startswith("1 history entry –"))
