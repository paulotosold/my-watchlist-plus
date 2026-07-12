import sqlite3
import unittest

from app.watch_states import (
    VALID_WATCH_STATES_BY_MEDIA_TYPE,
    validate_watch_state,
)
from db.connection import apply_database_schema


class WatchStateSchemaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_watch_state_is_nullable_and_null_can_keep_other_state(self):
        columns = {
            row["name"]: row
            for row in self.conn.execute("PRAGMA table_info(media_state)")
        }
        self.assertEqual(columns["watch_state"]["notnull"], 0)

        movie_id = self._insert_media(1, "movie", "Movie")
        self.conn.execute(
            """
            INSERT INTO media_state (
                media_id,
                watch_state,
                impression,
                is_collection_pick
            )
            VALUES (?, NULL, 'good', 1)
            """,
            (movie_id,),
        )

        row = self.conn.execute(
            "SELECT * FROM media_state WHERE media_id = ?",
            (movie_id,),
        ).fetchone()
        self.assertIsNone(row["watch_state"])
        self.assertEqual(row["impression"], "good")
        self.assertEqual(row["is_collection_pick"], 1)

    def test_removed_watching_and_suggested_states_are_rejected(self):
        movie_id = self._insert_media(2, "movie", "Movie")

        for watch_state in ("watching", "suggested"):
            with self.subTest(watch_state=watch_state):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(
                        """
                        INSERT INTO media_state (media_id, watch_state)
                        VALUES (?, ?)
                        """,
                        (movie_id, watch_state),
                    )

                with self.assertRaises(ValueError):
                    validate_watch_state("movie", watch_state)

    def test_schema_and_domain_validation_enforce_states_by_media_type(self):
        movie_id = self._insert_media(10, "movie", "Movie")
        series_id = self._insert_media(11, "series", "Series")
        episode_id = self._insert_media(12, "episode", "Episode")

        self.conn.execute(
            "INSERT INTO media_state (media_id, watch_state) VALUES (?, 'dropped')",
            (series_id,),
        )

        for media_id, media_type in (
            (movie_id, "movie"),
            (episode_id, "episode"),
        ):
            with self.subTest(media_type=media_type):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(
                        """
                        INSERT INTO media_state (media_id, watch_state)
                        VALUES (?, 'dropped')
                        """,
                        (media_id,),
                    )

                with self.assertRaises(ValueError):
                    validate_watch_state(media_type, "dropped")

        self.assertEqual(validate_watch_state("series", "dropped"), "dropped")
        self.assertIsNone(validate_watch_state("episode", None))

        self.assertEqual(
            VALID_WATCH_STATES_BY_MEDIA_TYPE,
            {
                "movie": frozenset({"to_watch", "watched", "not_interested"}),
                "series": frozenset({
                    "to_watch",
                    "watched",
                    "not_interested",
                    "dropped",
                }),
                "episode": frozenset({
                    "to_watch",
                    "watched",
                    "not_interested",
                }),
            },
        )

    def test_media_type_cannot_change_to_one_incompatible_with_state(self):
        series_id = self._insert_media(20, "series", "Series")
        self.conn.execute(
            "INSERT INTO media_state (media_id, watch_state) VALUES (?, 'dropped')",
            (series_id,),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE media SET media_type = 'movie' WHERE id = ?",
                (series_id,),
            )

        media_type = self.conn.execute(
            "SELECT media_type FROM media WHERE id = ?",
            (series_id,),
        ).fetchone()["media_type"]
        self.assertEqual(media_type, "series")

    def _insert_media(self, tmdb_id, media_type, title):
        cursor = self.conn.execute(
            """
            INSERT INTO media (tmdb_id, media_type, title)
            VALUES (?, ?, ?)
            """,
            (tmdb_id, media_type, title),
        )
        return cursor.lastrowid


if __name__ == "__main__":
    unittest.main()
