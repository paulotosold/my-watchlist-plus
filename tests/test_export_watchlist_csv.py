import csv
from datetime import date
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


import scripts.export_watchlist_csv as export_script
from db.connection import apply_database_schema


DEFAULT_IMDB_ID = object()


class ExportWatchlistCsvTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_collects_only_media_state_rows_and_formats_episode_title(self):
        self._insert_media(100, "movie", "Not in watchlist")
        later_id = self._insert_media(101, "movie", "same title")
        earlier_id = self._insert_media(102, "movie", "Same Title")
        series_id = self._insert_media(200, "series", "A Series")
        episode_id = self._insert_media(201, "episode", "Pilot")
        self.conn.execute(
            """
            INSERT INTO episode_details (
                media_id,
                series_id,
                season_num,
                episode_num
            )
            VALUES (?, ?, 1, 2)
            """,
            (episode_id, series_id),
        )
        self._insert_state(later_id, "watched", "good", 1)
        self._insert_state(earlier_id, "to_watch", None, None)
        self._insert_state(series_id, "dropped", "meh", 0)
        self._insert_state(episode_id, "watched", None, None)

        rows = export_script.collect_watchlist_rows(self.conn)

        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [row["title"] for row in rows],
            [
                "A Series",
                "A Series: Pilot S1:E2",
                "same title",
                "Same Title",
            ],
        )
        self.assertEqual(rows[0]["is_collection_pick"], "false")
        self.assertEqual(rows[1]["is_collection_pick"], "")
        self.assertEqual(rows[2]["is_collection_pick"], "true")
        self.assertEqual(rows[3]["impression"], "")

    def test_serializes_ordered_notes_history_and_lists_as_json(self):
        media_id = self._insert_media(
            300,
            "movie",
            'Árvore, "Especial"',
            imdb_id=None,
        )
        self._insert_state(media_id, "watched", "very_good", 1)
        self.conn.execute(
            """
            INSERT INTO media_notes (media_id, note, created_at)
            VALUES
                (?, 'second', '2026-01-02 00:00:00'),
                (?, ?, '2026-01-01 00:00:00')
            """,
            (media_id, media_id, 'first, "quoted"\nnext line'),
        )
        self.conn.execute(
            """
            INSERT INTO watch_history (
                media_id,
                date_earliest,
                date_latest,
                created_at
            )
            VALUES
                (?, NULL, '2026-02-02', '2026-01-02 00:00:00'),
                (?, '2025-01-01', NULL, '2026-01-01 00:00:00'),
                (?, NULL, NULL, '2026-01-03 00:00:00')
            """,
            (media_id, media_id, media_id),
        )
        upper_list_id = self._insert_list("Zulu")
        lower_list_id = self._insert_list('alpha, "group"')
        self.conn.executemany(
            "INSERT INTO media_lists (media_id, list_id) VALUES (?, ?)",
            (
                (media_id, upper_list_id),
                (media_id, lower_list_id),
            ),
        )

        row = export_script.collect_watchlist_rows(self.conn)[0]

        self.assertEqual(row["imdb_id"], "")
        self.assertEqual(
            json.loads(row["notes"]),
            ['first, "quoted"\nnext line', "second"],
        )
        self.assertEqual(
            json.loads(row["watch_history"]),
            ["2025-01-01:", ":2026-02-02", ":"],
        )
        self.assertEqual(
            json.loads(row["lists"]),
            ['alpha, "group"', "Zulu"],
        )

    def test_csv_round_trip_preserves_special_characters(self):
        row = self._empty_export_row()
        row["title"] = 'Árvore, "Especial"\nParte 2'
        row["notes"] = json.dumps(
            ['vírgula, aspas " e\nlinha'],
            ensure_ascii=False,
            separators=(",", ":"),
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            output_path = Path(temporary_dir) / "export.csv"
            export_script.write_csv_atomic([row], output_path)
            raw_contents = output_path.read_text(encoding="utf-8")
            parsed = list(csv.DictReader(StringIO(raw_contents)))

        self.assertEqual(tuple(parsed[0]), export_script.FIELDNAMES)
        self.assertEqual(parsed[0], {**row, "tmdb_id": "123"})

    def test_default_path_is_dated_and_atomic_write_overwrites(self):
        row = self._empty_export_row()

        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir)
            output_path = export_script.default_export_path(
                date(2026, 8, 13),
                data_dir,
            )
            self.assertEqual(
                output_path,
                data_dir / "media_export_2026-08-13.csv",
            )

            row["title"] = "First"
            export_script.write_csv_atomic([row], output_path)
            row["title"] = "Replacement"
            export_script.write_csv_atomic([row], output_path)

            with output_path.open(encoding="utf-8", newline="") as csv_file:
                parsed = list(csv.DictReader(csv_file))

            temporary_files = list(data_dir.glob(".*.tmp"))

        self.assertEqual([item["title"] for item in parsed], ["Replacement"])
        self.assertEqual(temporary_files, [])

    def test_main_rejects_missing_database_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            missing_path = Path(temporary_dir) / "missing.db"
            stderr = StringIO()

            with patch.object(export_script, "DB_PATH", missing_path), patch(
                "sys.stderr",
                stderr,
            ):
                exit_code = export_script.main()

            exists_after_main = missing_path.exists()

        self.assertEqual(exit_code, 1)
        self.assertFalse(exists_after_main)
        self.assertIn("database not found", stderr.getvalue())

    def _insert_media(
        self,
        tmdb_id,
        media_type,
        title,
        imdb_id=DEFAULT_IMDB_ID,
    ):
        if imdb_id is DEFAULT_IMDB_ID:
            imdb_id = f"tt{tmdb_id:07d}"

        cursor = self.conn.execute(
            """
            INSERT INTO media (tmdb_id, imdb_id, media_type, title)
            VALUES (?, ?, ?, ?)
            """,
            (tmdb_id, imdb_id, media_type, title),
        )
        return cursor.lastrowid

    def _insert_state(
        self,
        media_id,
        watch_state,
        impression,
        is_collection_pick,
    ):
        self.conn.execute(
            """
            INSERT INTO media_state (
                media_id,
                watch_state,
                impression,
                is_collection_pick
            )
            VALUES (?, ?, ?, ?)
            """,
            (media_id, watch_state, impression, is_collection_pick),
        )

    def _insert_list(self, name):
        cursor = self.conn.execute(
            "INSERT INTO lists (name) VALUES (?)",
            (name,),
        )
        return cursor.lastrowid

    def _empty_export_row(self):
        return {
            "imdb_id": "tt1234567",
            "tmdb_id": 123,
            "media_type": "movie",
            "title": "Title",
            "watch_state": "watched",
            "impression": "",
            "is_collection_pick": "",
            "notes": "[]",
            "watch_history": "[]",
            "lists": "[]",
        }


if __name__ == "__main__":
    unittest.main()
