import sqlite3
import unittest
from datetime import date

from app.filtered_media import (
    build_media_filter_query,
    get_media_rows_for_filter,
)
from app.library_filter import DEFAULT_FILTER_INTENT
from db.connection import apply_database_schema


class FilteredMediaFilterTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_default_filter_contains_only_released_to_watch_rows(self):
        today = date(2026, 7, 15)
        movie_id = self._insert_media(
            1,
            "movie",
            "Queued Movie",
            release_date="2026-07-14",
        )
        series_id = self._insert_media(
            2,
            "series",
            "Queued Series",
            release_date=today.isoformat(),
        )
        explicit_episode_id = self._insert_episode(
            series_id,
            3,
            "Queued Episode",
            1,
            1,
            release_date="2026-07-13",
        )
        neutral_episode_id = self._insert_episode(
            series_id,
            4,
            "Catalog Episode",
            1,
            2,
            release_date="2026-07-12",
        )
        watched_movie_id = self._insert_media(
            5,
            "movie",
            "Watched Movie",
            release_date="2026-07-11",
        )
        null_state_movie_id = self._insert_media(
            6,
            "movie",
            "Rated Only",
            release_date="2026-07-10",
        )
        future_movie_id = self._insert_media(
            7,
            "movie",
            "Coming Soon",
            release_date="2026-07-16",
        )
        unknown_date_movie_id = self._insert_media(
            8,
            "movie",
            "Release Unknown",
        )
        no_state_movie_id = self._insert_media(
            9,
            "movie",
            "Not Listed",
            release_date="2026-07-09",
        )

        for media_id in (
            movie_id,
            series_id,
            explicit_episode_id,
            future_movie_id,
            unknown_date_movie_id,
        ):
            self._insert_state(media_id, "to_watch")
        self._insert_state(watched_movie_id, "watched")
        self.conn.execute(
            """
            INSERT INTO media_state (media_id, watch_state, impression)
            VALUES (?, NULL, 'good')
            """,
            (null_state_movie_id,),
        )

        rows = get_media_rows_for_filter(
            self.conn,
            DEFAULT_FILTER_INTENT,
            today=today,
        )
        found_ids = {row["id"] for row in rows}

        self.assertEqual(
            found_ids,
            {movie_id, series_id, explicit_episode_id},
        )
        self.assertNotIn(neutral_episode_id, found_ids)
        self.assertNotIn(watched_movie_id, found_ids)
        self.assertNotIn(null_state_movie_id, found_ids)
        self.assertNotIn(future_movie_id, found_ids)
        self.assertNotIn(unknown_date_movie_id, found_ids)
        self.assertNotIn(no_state_movie_id, found_ids)

    def test_default_filter_uses_inclusive_date_and_random_order(self):
        query, params = build_media_filter_query(
            DEFAULT_FILTER_INTENT,
            today=date(2026, 7, 15),
        )
        normalized_query = " ".join(query.split())

        self.assertIn("m.release_date IS NOT NULL", normalized_query)
        self.assertIn("m.release_date <= ?", normalized_query)
        self.assertTrue(normalized_query.endswith("ORDER BY RANDOM()"))
        self.assertEqual(params, ["to_watch", "2026-07-15"])

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
                    build_media_filter_query({
                        "watch_state": {"include": [watch_state]},
                        "order_by": [{"field": "title"}],
                    })

    def _search_library(self, query):
        return get_media_rows_for_filter(
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
        release_date=None,
    ):
        cursor = self.conn.execute(
            """
            INSERT INTO media (
                tmdb_id,
                media_type,
                title,
                original_title,
                release_date
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (tmdb_id, media_type, title, original_title, release_date),
        )
        return cursor.lastrowid

    def _insert_episode(
        self,
        series_id,
        tmdb_id,
        title,
        season_num,
        episode_num,
        release_date=None,
    ):
        episode_id = self._insert_media(
            tmdb_id,
            "episode",
            title,
            release_date=release_date,
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
