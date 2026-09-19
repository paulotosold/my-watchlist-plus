import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.history.page import HistoryPage
from app.history.repository import (
    HISTORY_DEFAULT_FILTER_TEXT,
    HistoryEntry,
)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def make_entry(
    key,
    *,
    details_media_id=None,
    formatted_date=None,
):
    details_media_id = (
        details_media_id if details_media_id is not None else key + 1000
    )
    return HistoryEntry(
        key=("media_event", key),
        kind="media_event",
        entry_id=key,
        owner_media_ids=(key + 2000,),
        state_media_id=key + 2000,
        details_media_id=details_media_id,
        title=f"Movie {key}",
        date_earliest="2026-07-24",
        date_latest="2026-07-24",
        created_at=f"2026-07-24 20:{key % 60:02d}:00",
        release_date="2020-01-01",
        formatted_date=formatted_date or f"History date {key}",
        sort_key=(1, 3, (), key),
        poster=None,
        media_type="movie",
        watch_state="watched",
        impression="good",
        is_cabinet_worthy=False,
    )


class HistoryPageViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.source_entries = [
            make_entry(index)
            for index in range(180)
        ]
        self.connection_patch = patch(
            "app.history.page.get_connection",
            side_effect=lambda: FakeConnection(),
        )
        self.load_patch = patch(
            "app.history.page.load_default_history_entries",
            side_effect=lambda _conn: list(self.source_entries),
        )
        self.connection_patch.start()
        self.load_mock = self.load_patch.start()

        self.page = HistoryPage()
        self.page.resize(1000, 420)
        self.page.show()
        self._process_events()

    def tearDown(self):
        self.page.close()
        self.load_patch.stop()
        self.connection_patch.stop()
        self._process_events(2)

    def _process_events(self, count=8):
        for _ in range(count):
            self.application.processEvents()

    def _load_page(self):
        self.page.ensure_loaded()
        self._process_events()

    def _scroll_to_widget(self, widget, offset=5):
        scroll_bar = self.page.active_scroll_area.verticalScrollBar()
        scroll_bar.setValue(widget.geometry().top() + offset)
        self._process_events(2)
        return self.page._capture_scroll_anchor()

    def _assert_active_entry_visible(self, entry_key):
        target = next(
            widget
            for widget in self.page._active_entry_widgets()
            if widget.entry.key == entry_key
        )
        scroll_area = self.page.active_scroll_area
        scroll_value = scroll_area.verticalScrollBar().value()
        viewport_bottom = (
            scroll_value + scroll_area.viewport().height() - 1
        )

        self.assertGreaterEqual(target.geometry().bottom(), scroll_value)
        self.assertLessEqual(target.geometry().top(), viewport_bottom)

    def test_grid_keeps_repository_order_and_forwards_tile_details(self):
        requested_order = [
            17,
            3,
            80,
            2,
            19,
            5,
            7,
            1,
            11,
            13,
            23,
            29,
            31,
            37,
            41,
            43,
            47,
            53,
            59,
            61,
        ]
        self.source_entries = [
            make_entry(key, details_media_id=9000 + key)
            for key in requested_order
        ]
        self._load_page()
        self._process_events()

        self.assertEqual(
            [tile.entry for tile in self.page.grid_board.tiles],
            self.source_entries,
        )
        self.assertEqual(
            self.page.grid_board.tiles[10].geometry().left(),
            self.page.grid_board.tiles[0].geometry().left(),
        )
        self.assertGreater(
            self.page.grid_board.tiles[10].geometry().top(),
            self.page.grid_board.tiles[0].geometry().top(),
        )

        details_spy = QSignalSpy(self.page.details_requested)
        self.page.grid_board.tiles[2].poster_label.request_details()

        self.assertEqual(details_spy.count(), 1)
        self.assertEqual(details_spy.at(0), [9080])

    def test_grid_anchor_stays_visible_across_density_and_resize(self):
        self._load_page()
        self._process_events()
        anchor = self._scroll_to_widget(
            self.page.grid_board.tiles[90],
            offset=7,
        )

        self.assertTrue(self.page.set_posters_per_row(6))
        self._process_events()
        self._assert_active_entry_visible(anchor[0])

        anchor = self.page._capture_scroll_anchor()
        self.assertTrue(self.page.set_posters_per_row(25))
        self._process_events()
        self._assert_active_entry_visible(anchor[0])

        self.page.set_posters_per_row(6)
        self._process_events()
        anchor = self._scroll_to_widget(
            self.page.grid_board.tiles[96],
            offset=9,
        )
        old_tile_width = self.page.grid_board.tile_width

        self.page.resize(760, 420)
        self._process_events(12)

        self.assertNotEqual(
            self.page.grid_board.tile_width,
            old_tile_width,
        )
        self._assert_active_entry_visible(anchor[0])

    def test_default_filter_cancels_a_pending_anchor_restore(self):
        self._load_page()
        self.page.set_posters_per_row(6)
        self._process_events()
        grid_scroll_bar = self.page.grid_scroll_area.verticalScrollBar()
        grid_scroll_bar.setValue(
            self.page.grid_board.tiles[90].geometry().top() + 7
        )

        self.page.set_posters_per_row(25)
        self.page.on_filter_input(HISTORY_DEFAULT_FILTER_TEXT)
        self._process_events()

        self.assertEqual(self.load_mock.call_count, 2)
        self.assertEqual(
            self.page.grid_scroll_area.verticalScrollBar().value(),
            0,
        )
        self.assertEqual(grid_scroll_bar.value(), 0)

    def test_refresh_falls_back_to_nearest_surviving_entry_key(self):
        self._load_page()
        removed_widget = self.page.grid_board.tiles[70]
        removed_key = removed_widget.entry.key
        next_surviving_key = self.source_entries[71].key
        self._scroll_to_widget(removed_widget, offset=11)
        inserted_entries = [
            make_entry(1000),
            make_entry(1001),
        ]
        self.source_entries = (
            inserted_entries
            + [
                entry
                for entry in self.source_entries
                if entry.key != removed_key
            ]
        )

        self.page.invalidate()
        self.page.ensure_loaded()
        self._process_events()

        self._assert_active_entry_visible(next_surviving_key)

    def test_density_survives_inactivity_and_refresh(self):
        self._load_page()
        self.page.set_posters_per_row(6)
        self._process_events()

        self.page.hide()
        self._process_events(2)
        self.page.ensure_loaded()
        self.page.show()
        self._process_events()

        self.assertEqual(self.load_mock.call_count, 1)
        self.assertEqual(self.page.posters_per_row, 6)

        self.source_entries = [
            make_entry(index)
            for index in range(250, 430)
        ]
        self.page.invalidate()
        self.page.ensure_loaded()
        self._process_events()

        self.assertEqual(self.load_mock.call_count, 2)
        self.assertEqual(self.page.posters_per_row, 6)
        self.assertEqual(
            self.page.grid_board.entries,
            self.source_entries,
        )
        self.assertEqual(
            [tile.entry for tile in self.page.grid_board.tiles],
            self.source_entries,
        )


if __name__ == "__main__":
    unittest.main()
