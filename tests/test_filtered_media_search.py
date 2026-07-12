import sqlite3
import unittest

from app.filtered_media import (
    DEFAULT_SEARCH_INTENT,
    build_media_search_query,
    get_media_rows_for_search,
)
from db.connection import apply_database_schema


class FilteredMediaSearchTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_default_filter_contains_only_explicit_to_watch_rows(self):
        movie_id = self._insert_media(1, "movie", "Queued Movie")
        series_id = self._insert_media(2, "series", "Queued Series")
        explicit_episode_id = self._insert_episode(
            series_id,
            3,
            "Queued Episode",
            1,
            1,
        )
        neutral_episode_id = self._insert_episode(
            series_id,
            4,
            "Catalog Episode",
            1,
            2,
        )
        watched_movie_id = self._insert_media(5, "movie", "Watched Movie")
        null_state_movie_id = self._insert_media(6, "movie", "Rated Only")

        for media_id in (movie_id, series_id, explicit_episode_id):
            self._insert_state(media_id, "to_watch")
        self._insert_state(watched_movie_id, "watched")
        self.conn.execute(
            """
            INSERT INTO media_state (media_id, watch_state, impression)
            VALUES (?, NULL, 'good')
            """,
            (null_state_movie_id,),
        )

        rows = get_media_rows_for_search(self.conn, DEFAULT_SEARCH_INTENT)
        found_ids = {row["id"] for row in rows}

        self.assertEqual(
            found_ids,
            {movie_id, series_id, explicit_episode_id},
        )
        self.assertNotIn(neutral_episode_id, found_ids)
        self.assertNotIn(watched_movie_id, found_ids)
        self.assertNotIn(null_state_movie_id, found_ids)

    def test_library_search_matches_title_parent_and_episode_code(self):
        series_id = self._insert_media(
            10,
            "series",
            "The Expanse",
            original_title="A Expansao",
        )
        first_episode_id = self._insert_episode(
            series_id,
            11,
            "Dulcinea",
            1,
            1,
        )
        second_episode_id = self._insert_episode(
            series_id,
            12,
            "The Big Empty",
            1,
            2,
        )
        unrelated_id = self._insert_media(13, "movie", "Arrival")

        title_rows = self._search_library("dulcinea")
        self.assertEqual([row["id"] for row in title_rows], [first_episode_id])

        parent_rows = self._search_library("the expanse")
        self.assertEqual(
            {row["id"] for row in parent_rows},
            {series_id, first_episode_id, second_episode_id},
        )

        original_parent_rows = self._search_library("a expansao")
        self.assertEqual(
            {row["id"] for row in original_parent_rows},
            {series_id, first_episode_id, second_episode_id},
        )

        coded_rows = self._search_library("The Expanse S01E02")
        self.assertEqual([row["id"] for row in coded_rows], [second_episode_id])

        compact_code_rows = self._search_library("s1e1")
        self.assertEqual([row["id"] for row in compact_code_rows], [first_episode_id])
        self.assertNotIn(unrelated_id, {row["id"] for row in coded_rows})

        for row in title_rows + coded_rows:
            self.assertIsNone(row["resolved_watch_state"])

    def test_removed_states_are_not_accepted_by_filters(self):
        for watch_state in ("watching", "suggested"):
            with self.subTest(watch_state=watch_state):
                with self.assertRaises(ValueError):
                    build_media_search_query({
                        "watch_state": {"include": [watch_state]},
                        "order_by": [{"field": "title"}],
                    })

    def _search_library(self, query):
        return get_media_rows_for_search(
            self.conn,
            {
                "library_query": query,
                "order_by": [{"field": "title"}],
            },
        )

    def _insert_media(
        self,
        tmdb_id,
        media_type,
        title,
        original_title=None,
    ):
        cursor = self.conn.execute(
            """
            INSERT INTO media (
                tmdb_id,
                media_type,
                title,
                original_title
            )
            VALUES (?, ?, ?, ?)
            """,
            (tmdb_id, media_type, title, original_title),
        )
        return cursor.lastrowid

    def _insert_episode(
        self,
        series_id,
        tmdb_id,
        title,
        season_num,
        episode_num,
    ):
        episode_id = self._insert_media(tmdb_id, "episode", title)
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

    def _insert_state(self, media_id, watch_state):
        self.conn.execute(
            """
            INSERT INTO media_state (media_id, watch_state)
            VALUES (?, ?)
            """,
            (media_id, watch_state),
        )


if __name__ == "__main__":
    unittest.main()
