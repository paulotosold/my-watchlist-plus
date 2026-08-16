import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QAbstractButton, QApplication

from app.history.constants import (
    DEFAULT_HISTORY_POSTERS_PER_ROW,
    MAX_HISTORY_POSTERS_PER_ROW,
    MIN_HISTORY_POSTERS_PER_ROW,
)
from app.history.grid import (
    GRID_BOTTOM_MARGIN,
    GRID_SPACING,
    GRID_TOP_MARGIN,
    HistoryGridBoard,
)
from app.history.repository import HistoryEntry


def make_entry(
    key,
    *,
    details_media_id=None,
    title=None,
    formatted_date=None,
    poster=None,
):
    details_media_id = details_media_id or key
    return HistoryEntry(
        key=("media_event", key),
        kind="media_event",
        watch_history_ids=(key,),
        owner_media_ids=(details_media_id,),
        state_media_id=details_media_id,
        details_media_id=details_media_id,
        title=title or f"Movie {key}",
        date_earliest="2026-07-24",
        date_latest="2026-07-24",
        created_at="2026-07-24 20:00:00",
        release_date="2020-01-01",
        formatted_date=formatted_date or "24 Jul 2026, Fri",
        sort_key=(1, 3, (), key),
        poster=poster,
        media_type="movie",
        watch_state="watched",
        impression="good",
        is_cabinet_worthy=False,
    )


class HistoryGridBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.board = HistoryGridBoard()
        self.board.resize(1000, 400)
        self.board.show()
        self._process_layout_events()

    def tearDown(self):
        self.board.close()
        self._process_layout_events()

    def _process_layout_events(self):
        for _ in range(4):
            self.application.processEvents()

    def test_defaults_limits_spacing_and_fixed_poster_ratio(self):
        self.assertEqual(
            self.board.posters_per_row,
            DEFAULT_HISTORY_POSTERS_PER_ROW,
        )
        self.assertEqual(DEFAULT_HISTORY_POSTERS_PER_ROW, 18)
        self.assertEqual(MIN_HISTORY_POSTERS_PER_ROW, 6)
        self.assertEqual(MAX_HISTORY_POSTERS_PER_ROW, 24)
        self.assertEqual(
            self.board.grid_layout.horizontalSpacing(),
            GRID_SPACING,
        )
        self.assertEqual(
            self.board.grid_layout.verticalSpacing(),
            GRID_SPACING,
        )
        self.assertEqual(GRID_SPACING, 6)

        self.board.set_entries([make_entry(index) for index in range(20)])
        self._process_layout_events()

        self.assertEqual(self.board.row_count, 2)
        self.assertEqual(
            self.board.tile_height,
            round(self.board.tile_width * 1.5),
        )
        self.assertEqual(
            self.board.tiles[18].geometry().left(),
            self.board.tiles[0].geometry().left(),
        )
        self.assertEqual(
            self.board.tiles[0].geometry().top(),
            GRID_TOP_MARGIN,
        )
        self.assertEqual(
            self.board.tiles[1].geometry().left()
            - self.board.tiles[0].geometry().right()
            - 1,
            GRID_SPACING,
        )
        self.assertEqual(
            self.board.tiles[18].geometry().top()
            - self.board.tiles[0].geometry().bottom()
            - 1,
            GRID_SPACING,
        )
        self.assertEqual(
            self.board.content_height,
            GRID_TOP_MARGIN
            + self.board.row_count * self.board.tile_height
            + GRID_SPACING
            + GRID_BOTTOM_MARGIN,
        )
        self.assertEqual(self.board.minimumHeight(), self.board.content_height)
        self.assertEqual(
            self.board.minimumHeight()
            - self.board.tiles[-1].geometry().bottom()
            - 1,
            GRID_BOTTOM_MARGIN,
        )

    def test_entries_stay_row_major_and_expose_key_lookups(self):
        entries = [
            make_entry(7),
            make_entry(3),
            make_entry(7, details_media_id=99),
            make_entry(1),
        ]
        # History keys are normally unique watch events. This duplicate exercises
        # the plural mapping without changing the requested chronological order.
        entries[2] = replace(entries[2], key=entries[0].key)

        self.board.set_entries(entries)
        self._process_layout_events()

        self.assertEqual(self.board.entries, entries)
        self.assertEqual(
            [tile.entry for tile in self.board.tiles],
            entries,
        )
        self.assertIs(
            self.board.tile_by_entry_key[entries[0].key],
            self.board.tiles[0],
        )
        self.assertEqual(
            self.board.tiles_by_entry_key[entries[0].key],
            self.board.tiles[:1] + self.board.tiles[2:3],
        )
        self.assertEqual(
            self.board.entry_index_by_key[entries[0].key],
            0,
        )

    def test_density_clamps_and_reuses_tiles(self):
        self.board.set_entries([make_entry(index) for index in range(30)])
        original_tiles = list(self.board.tiles)

        self.assertTrue(self.board.set_posters_per_row(2))
        self.assertEqual(
            self.board.posters_per_row,
            MIN_HISTORY_POSTERS_PER_ROW,
        )
        self.assertEqual(self.board.tiles, original_tiles)
        self.assertEqual(self.board.row_count, 5)

        self.assertTrue(self.board.set_posters_per_row(99))
        self.assertEqual(
            self.board.posters_per_row,
            MAX_HISTORY_POSTERS_PER_ROW,
        )
        self.assertEqual(self.board.tiles, original_tiles)
        self.assertEqual(self.board.row_count, 2)
        self.assertFalse(
            self.board.set_posters_per_row(
                MAX_HISTORY_POSTERS_PER_ROW
            )
        )

    def test_refresh_reuses_surviving_entry_tiles_in_new_order(self):
        original_entries = [make_entry(index) for index in range(6)]
        self.board.set_entries(original_entries)
        original_by_key = dict(self.board.tile_by_entry_key)
        refreshed_entries = [
            replace(original_entries[4], formatted_date="Jul 2026"),
            original_entries[1],
            make_entry(20),
        ]

        self.board.set_entries(refreshed_entries)

        self.assertIs(
            self.board.tiles[0],
            original_by_key[original_entries[4].key],
        )
        self.assertIs(
            self.board.tiles[1],
            original_by_key[original_entries[1].key],
        )
        self.assertEqual(self.board.tiles[0].toolTip(), "Jul 2026")
        self.assertEqual(
            [tile.entry for tile in self.board.tiles],
            refreshed_entries,
        )

    def test_layout_width_and_widget_resize_reflow_tiles(self):
        self.board.set_entries([make_entry(index) for index in range(20)])
        initial_width = self.board.tile_width

        self.assertTrue(self.board.set_layout_width(700))
        self.assertLess(self.board.tile_width, initial_width)
        limited_width = self.board.tile_width
        self.assertFalse(self.board.set_layout_width(700))

        self.assertTrue(self.board.set_layout_width(None))
        self.assertGreater(self.board.tile_width, limited_width)
        self.board.resize(800, 400)
        self._process_layout_events()
        self.assertLess(self.board.tile_width, initial_width)

    def test_tooltip_and_mouse_keyboard_activation_forward_media_id(self):
        entry = make_entry(
            1,
            details_media_id=42,
            formatted_date="Jan 2026",
        )
        self.board.set_entries([entry])
        self._process_layout_events()
        tile = self.board.tiles[0]
        board_spy = QSignalSpy(self.board.details_requested)
        tile_spy = QSignalSpy(tile.details_requested)

        self.assertEqual(tile.toolTip(), "Jan 2026")
        QTest.mouseClick(
            tile,
            Qt.MouseButton.LeftButton,
            pos=QPoint(tile.width() // 2, tile.height() // 2),
        )
        tile.setFocus(Qt.FocusReason.TabFocusReason)
        QTest.keyClick(tile, Qt.Key.Key_Return)
        QTest.keyClick(tile, Qt.Key.Key_Space)

        self.assertEqual(tile_spy.count(), 3)
        self.assertEqual(board_spy.count(), 3)
        self.assertTrue(all(
            board_spy.at(index) == [42]
            for index in range(board_spy.count())
        ))

    def test_placeholder_is_clickable_and_grid_has_no_buttons_or_overlays(self):
        self.board.set_entries([make_entry(1, details_media_id=77)])
        self._process_layout_events()
        tile = self.board.tiles[0]
        spy = QSignalSpy(self.board.details_requested)

        self.assertEqual(tile.text().replace("\n", " "), "No poster")
        self.assertEqual(tile.findChildren(QAbstractButton), [])
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton)

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0), [77])

        self.board.set_posters_per_row(MAX_HISTORY_POSTERS_PER_ROW)
        self._process_layout_events()
        widest_line = max(
            tile.fontMetrics().horizontalAdvance(line)
            for line in tile.text().splitlines()
        )
        self.assertLessEqual(widest_line, tile.width() - 4)

    def test_local_poster_is_rendered_into_the_fixed_tile(self):
        with tempfile.TemporaryDirectory() as directory:
            poster_path = Path(directory) / "poster.png"
            image = QImage(200, 400, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGray)
            self.assertTrue(image.save(str(poster_path)))
            entry = make_entry(
                1,
                poster={"filename": "/poster.png"},
            )

            with patch("app.history.grid.POSTER_DIR", Path(directory)):
                self.board.set_entries([entry])
                self._process_layout_events()

            tile = self.board.tiles[0]
            self.assertEqual(tile.text(), "")
            self.assertFalse(tile.pixmap().isNull())
            self.assertEqual(tile.pixmap().size(), tile.size())

            with patch("app.history.grid._read_scaled_poster") as read:
                self.board.set_entries([entry])

            read.assert_not_called()

    def test_missing_poster_is_loaded_when_file_appears_on_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            entry = make_entry(
                1,
                poster={"filename": "later.png"},
            )

            with patch("app.history.grid.POSTER_DIR", Path(directory)):
                self.board.set_entries([entry])
                self._process_layout_events()
                tile = self.board.tiles[0]
                self.assertEqual(
                    tile.text().replace("\n", " "),
                    "No poster",
                )

                image = QImage(200, 300, QImage.Format.Format_RGB32)
                image.fill(Qt.GlobalColor.darkGray)
                self.assertTrue(
                    image.save(str(Path(directory) / "later.png"))
                )
                self.board.set_entries([entry])
                self._process_layout_events()

            self.assertEqual(tile.text(), "")
            self.assertFalse(tile.pixmap().isNull())


if __name__ == "__main__":
    unittest.main()
