import sqlite3
import unittest

import app.media_repository as media_repository
from db.connection import apply_database_schema


class MediaRepositoryWatchHistoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_sync_series_episode_watch_history_updates_inserts_and_deletes(self):
        series_id = self._insert_media(1, "series", "Example")
        episode_1 = self._insert_episode(series_id, 11, 1, 1)
        episode_2 = self._insert_episode(series_id, 12, 1, 2)
        episode_3 = self._insert_episode(series_id, 13, 1, 3)
        other_series_id = self._insert_media(2, "series", "Other")
        other_episode = self._insert_episode(other_series_id, 21, 1, 1)

        keep_and_update_id = self._insert_watch_history(
            episode_1,
            "2026-05-01",
            "2026-05-01",
        )
        delete_id = self._insert_watch_history(
            episode_2,
            "2026-05-02",
            "2026-05-02",
        )
        keep_existing_id = self._insert_watch_history(
            episode_2,
            "2026-05-03",
            "2026-05-03",
        )
        other_series_watch_history_id = self._insert_watch_history(
            other_episode,
            "2026-05-04",
            "2026-05-04",
        )

        media_repository.sync_series_episode_watch_history(self.conn, series_id, [
            {
                "episode_id": episode_1,
                "watch_history_id": keep_and_update_id,
                "season_num": 1,
                "episode_num": 1,
                "date_earliest": "2026-05-10",
                "date_latest": "2026-05-10",
            },
            {
                "episode_id": episode_2,
                "watch_history_id": keep_existing_id,
                "season_num": 1,
                "episode_num": 2,
                "date_earliest": "2026-05-03",
                "date_latest": "2026-05-03",
            },
            {
                "season_num": 1,
                "episode_num": 3,
                "date_earliest": "2026-05-11",
                "date_latest": "2026-05-11",
            },
        ])

        rows = self._watch_history_rows()
        self.assertNotIn(delete_id, rows)
        self.assertIn(other_series_watch_history_id, rows)
        self.assertEqual(rows[keep_and_update_id]["date_earliest"], "2026-05-10")
        self.assertEqual(rows[keep_existing_id]["date_earliest"], "2026-05-03")

        inserted_rows = [
            row
            for row in rows.values()
            if row["media_id"] == episode_3
        ]
        self.assertEqual(len(inserted_rows), 1)
        self.assertEqual(inserted_rows[0]["date_earliest"], "2026-05-11")

    def _insert_media(self, tmdb_id, media_type, title):
        cursor = self.conn.execute(
            """
            INSERT INTO media (
                tmdb_id,
                media_type,
                title
            )
            VALUES (?, ?, ?)
            """,
            (tmdb_id, media_type, title),
        )
        return cursor.lastrowid

    def _insert_episode(self, series_id, tmdb_id, season_num, episode_num):
        episode_id = self._insert_media(
            tmdb_id,
            "episode",
            f"S{season_num}E{episode_num}",
        )
        self.conn.execute(
            """
            INSERT INTO episode_details (
                media_id,
                series_id,
                season_num,
                episode_num
            )
            VALUES (?, ?, ?, ?)
            """,
            (episode_id, series_id, season_num, episode_num),
        )
        return episode_id

    def _insert_watch_history(self, media_id, date_earliest, date_latest):
        cursor = self.conn.execute(
            """
            INSERT INTO watch_history (
                media_id,
                date_earliest,
                date_latest
            )
            VALUES (?, ?, ?)
            """,
            (media_id, date_earliest, date_latest),
        )
        return cursor.lastrowid

    def _watch_history_rows(self):
        cursor = self.conn.execute(
            """
            SELECT
                id,
                media_id,
                date_earliest,
                date_latest
            FROM watch_history
            """
        )
        return {
            row["id"]: dict(row)
            for row in cursor.fetchall()
        }


if __name__ == "__main__":
    unittest.main()
