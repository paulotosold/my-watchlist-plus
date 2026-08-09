import copy
import sqlite3
import unittest
from unittest.mock import patch

import app.media_repository as media_repository
from app.media_repository import user_data as media_user_data_repository
from db.connection import apply_database_schema


class MediaRepositoryIncrementalSaveTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_scalar_patch_preserves_unrelated_concurrent_field(self):
        media_id = self._insert_media(1, "movie", "Movie")
        self.conn.execute(
            """
            INSERT INTO media_state (media_id, watch_state, impression)
            VALUES (?, 'to_watch', 'good')
            """,
            (media_id,),
        )
        baseline = self._draft(media_id, 1, "movie")
        baseline["user_data"].update({
            "watch_state": "to_watch",
            "impression": "good",
        })
        current = copy.deepcopy(baseline)
        current["user_data"]["impression"] = "very_good"
        self.conn.execute(
            "UPDATE media_state SET watch_state = 'watched' WHERE media_id = ?",
            (media_id,),
        )

        result = media_repository.apply_media_user_changes(
            self.conn,
            media_id,
            baseline,
            current,
        )

        row = self.conn.execute(
            "SELECT watch_state, impression FROM media_state WHERE media_id = ?",
            (media_id,),
        ).fetchone()
        self.assertEqual(dict(row), {
            "watch_state": "watched",
            "impression": "very_good",
        })
        self.assertEqual(result["counts"]["state_fields_updated"], 1)

    def test_same_scalar_field_concurrent_edit_raises(self):
        media_id = self._insert_media(2, "movie", "Movie")
        self.conn.execute(
            "INSERT INTO media_state (media_id, impression) VALUES (?, 'good')",
            (media_id,),
        )
        baseline = self._draft(media_id, 2, "movie")
        baseline["user_data"]["impression"] = "good"
        current = copy.deepcopy(baseline)
        current["user_data"]["impression"] = "very_good"
        self.conn.execute(
            "UPDATE media_state SET impression = 'meh' WHERE media_id = ?",
            (media_id,),
        )

        with self.assertRaises(media_repository.ConcurrentEditError):
            media_repository.apply_media_user_changes(
                self.conn,
                media_id,
                baseline,
                current,
            )

    def test_history_delta_preserves_external_rows_and_returns_new_id(self):
        media_id = self._insert_media(3, "movie", "Movie")
        baseline_id = self._insert_history(media_id, "2026-01-01")
        baseline = self._draft(media_id, 3, "movie")
        baseline["user_data"]["watch_history"] = [{
            "id": baseline_id,
            "date_earliest": "2026-01-01",
            "date_latest": "2026-01-01",
        }]
        current = copy.deepcopy(baseline)
        current["user_data"]["watch_history"] = [{
            "draft_id": "new-event",
            "date_earliest": "2026-01-02",
            "date_latest": "2026-01-02",
        }]
        external_id = self._insert_history(media_id, "2026-01-03")

        result = media_repository.apply_media_user_changes(
            self.conn,
            media_id,
            baseline,
            current,
        )

        rows = self.conn.execute(
            "SELECT id, date_earliest FROM watch_history WHERE media_id = ?",
            (media_id,),
        ).fetchall()
        rows_by_id = {row["id"]: row["date_earliest"] for row in rows}
        new_id = result["inserted_ids_by_draft_id"]["media_watch_history"][
            "new-event"
        ]
        self.assertNotIn(baseline_id, rows_by_id)
        self.assertEqual(rows_by_id[external_id], "2026-01-03")
        self.assertEqual(rows_by_id[new_id], "2026-01-02")
        self.assertNotIn("id", current["user_data"]["watch_history"][0])

    def test_series_history_only_transitions_affected_episode(self):
        series_id = self._insert_media(10, "series", "Series")
        episode_1 = self._insert_episode(series_id, 11, 1, 1)
        episode_2 = self._insert_episode(series_id, 12, 1, 2)
        self.conn.execute(
            "INSERT INTO media_state (media_id, watch_state) VALUES (?, 'to_watch')",
            (episode_2,),
        )
        baseline = self._draft(series_id, 10, "series")
        current = copy.deepcopy(baseline)
        current["series_view"] = {"episode_watch_history": [{
            "draft_id": "episode-event",
            "episode_id": episode_1,
            "season_num": 1,
            "episode_num": 1,
            "date_earliest": None,
            "date_latest": None,
        }]}

        media_repository.apply_media_user_changes(
            self.conn,
            series_id,
            baseline,
            current,
        )

        states = {
            row["media_id"]: row["watch_state"]
            for row in self.conn.execute(
                "SELECT media_id, watch_state FROM media_state"
            ).fetchall()
        }
        self.assertEqual(states[episode_1], "watched")
        self.assertEqual(states[episode_2], "to_watch")

    def test_impression_only_skips_every_history_domain(self):
        series_id = self._insert_media(20, "series", "Series")
        episode_id = self._insert_episode(series_id, 21, 1, 1)
        history_id = self._insert_history(episode_id, "2026-01-01")
        baseline = self._draft(series_id, 20, "series")
        baseline["series_view"]["episode_watch_history"] = [{
            "watch_history_id": history_id,
            "episode_id": episode_id,
            "season_num": 1,
            "episode_num": 1,
            "date_earliest": "2026-01-01",
            "date_latest": "2026-01-01",
        }]
        current = copy.deepcopy(baseline)
        current["user_data"]["impression"] = "very_good"

        with patch.object(
            media_user_data_repository,
            "_apply_owned_row_delta",
            wraps=media_user_data_repository._apply_owned_row_delta,
        ) as direct_delta, patch.object(
            media_user_data_repository,
            "_apply_series_episode_history_delta",
            wraps=media_user_data_repository._apply_series_episode_history_delta,
        ) as episode_delta:
            result = media_repository.apply_media_user_changes(
                self.conn,
                series_id,
                baseline,
                current,
            )

        direct_delta.assert_not_called()
        episode_delta.assert_not_called()
        self.assertEqual(result["counts"]["state_fields_updated"], 1)
        self.assertEqual(
            self.conn.execute(
                "SELECT impression FROM media_state WHERE media_id = ?",
                (series_id,),
            ).fetchone()["impression"],
            "very_good",
        )

    def _draft(self, media_id, tmdb_id, media_type):
        return {
            "media_id": media_id,
            "metadata": {
                "tmdb_id": tmdb_id,
                "media_type": media_type,
            },
            "series_view": ({"episode_watch_history": []}
                            if media_type == "series" else None),
            "user_data": media_repository.get_empty_media_user_data(),
        }

    def _insert_media(self, tmdb_id, media_type, title):
        return self.conn.execute(
            "INSERT INTO media (tmdb_id, media_type, title) VALUES (?, ?, ?)",
            (tmdb_id, media_type, title),
        ).lastrowid

    def _insert_episode(self, series_id, tmdb_id, season_num, episode_num):
        episode_id = self._insert_media(tmdb_id, "episode", "Episode")
        self.conn.execute(
            """
            INSERT INTO episode_details
                (media_id, series_id, season_num, episode_num)
            VALUES (?, ?, ?, ?)
            """,
            (episode_id, series_id, season_num, episode_num),
        )
        return episode_id

    def _insert_history(self, media_id, date):
        return self.conn.execute(
            """
            INSERT INTO watch_history (media_id, date_earliest, date_latest)
            VALUES (?, ?, ?)
            """,
            (media_id, date, date),
        ).lastrowid


class MediaRepositoryMetadataRefreshTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_series_refresh_updates_inserts_preserves_and_renumbers(self):
        series_id = self._insert_media(100, "series", "Old Series")
        first_id = self._insert_episode(series_id, 101, 1, 1, "Old One", "tt101")
        second_id = self._insert_episode(series_id, 102, 1, 2, "Old Two", "tt102")
        absent_id = self._insert_episode(series_id, 103, 1, 3, "Local Only", "tt103")
        history_id = self.conn.execute(
            "INSERT INTO watch_history (media_id) VALUES (?)",
            (first_id,),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO media_state (media_id, impression) VALUES (?, 'good')",
            (first_id,),
        )
        self.conn.execute(
            "INSERT INTO media_notes (media_id, note) VALUES (?, 'keep me')",
            (first_id,),
        )
        self.conn.execute(
            """
            INSERT INTO media_watch_providers (
                media_id, provider_tmdb_id, provider_name, country_code, access_type
            ) VALUES (?, 8, 'Provider', 'US', 'flatrate')
            """,
            (first_id,),
        )
        self.conn.execute(
            """
            INSERT INTO media_posters (
                media_id, filename, source, curation_status, is_default
            ) VALUES (?, 'poster.jpg', 'tmdb', 'pending', 0)
            """,
            (first_id,),
        )
        self.conn.execute(
            "INSERT INTO people (tmdb_id, name) VALUES (900, 'Episode Director')"
        )
        director_id = self.conn.execute(
            "SELECT id FROM people WHERE tmdb_id = 900"
        ).fetchone()["id"]
        self.conn.execute(
            "INSERT INTO media_directors (media_id, person_id) VALUES (?, ?)",
            (first_id, director_id),
        )
        snapshot = self._series_snapshot([
            self._episode_metadata(101, 1, 2, "New One"),
            self._episode_metadata(102, 1, 1, "New Two"),
            self._episode_metadata(104, 2, 1, "Brand New"),
        ])

        result = media_repository.apply_metadata_refresh(
            self.conn,
            series_id,
            snapshot,
        )

        positions = {
            row["tmdb_id"]: (row["episode_id"], row["season_num"], row["episode_num"])
            for row in result["episodes"]
        }
        self.assertEqual(positions[101], (first_id, 1, 2))
        self.assertEqual(positions[102], (second_id, 1, 1))
        self.assertEqual(positions[103], (absent_id, 1, 3))
        self.assertIn(104, positions)
        self.assertEqual(result["stats"]["episodes_created"], 1)
        self.assertEqual(result["stats"]["episodes_absent_preserved"], 1)
        self.assertEqual(
            self.conn.execute(
                "SELECT imdb_id FROM media WHERE id = ?", (first_id,)
            ).fetchone()["imdb_id"],
            "tt101",
        )
        self.assertIsNotNone(self.conn.execute(
            "SELECT 1 FROM media_directors WHERE media_id = ?", (first_id,)
        ).fetchone())
        self.assertIsNotNone(self.conn.execute(
            "SELECT 1 FROM watch_history WHERE id = ?", (history_id,)
        ).fetchone())
        self.assertEqual(self.conn.execute(
            "SELECT impression FROM media_state WHERE media_id = ?", (first_id,)
        ).fetchone()["impression"], "good")
        self.assertEqual(
            self.conn.execute(
                "SELECT note FROM media_notes WHERE media_id = ?",
                (first_id,),
            ).fetchone()["note"],
            "keep me",
        )
        self.assertIsNotNone(self.conn.execute(
            "SELECT 1 FROM media_watch_providers WHERE media_id = ?",
            (first_id,),
        ).fetchone())
        self.assertIsNotNone(self.conn.execute(
            "SELECT 1 FROM media_posters WHERE media_id = ?",
            (first_id,),
        ).fetchone())

    def test_series_refresh_rejects_position_owned_by_absent_episode(self):
        series_id = self._insert_media(200, "series", "Series")
        self._insert_episode(series_id, 201, 1, 1, "One", None)
        snapshot = self._series_snapshot([
            self._episode_metadata(202, 1, 1, "Replacement"),
        ], tmdb_id=200)

        with self.assertRaises(media_repository.MetadataRefreshConflict):
            media_repository.apply_metadata_refresh(
                self.conn,
                series_id,
                snapshot,
            )

    def _series_snapshot(self, episodes, tmdb_id=100):
        return {
            "media_type": "series",
            "tmdb_id": tmdb_id,
            "checked_at": "2026-07-13 10:00:00",
            "metadata": {
                "tmdb_id": tmdb_id,
                "imdb_id": f"tt{tmdb_id}",
                "media_type": "series",
                "title": "New Series",
                "original_title": "New Series",
                "production_status": "Returning Series",
                "release_date": "2025-01-01",
                "runtime_min": None,
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "directors": [],
                "creators": [],
                "writers": [],
                "actors": [],
                "episode_details": None,
            },
            "regular_episodes": episodes,
            "series_summary": None,
            "loaded_fields": {},
        }

    def _episode_metadata(self, tmdb_id, season, episode, title):
        return {
            "tmdb_id": tmdb_id,
            "imdb_id": None,
            "media_type": "episode",
            "title": title,
            "original_title": title,
            "production_status": "Returning Series",
            "release_date": "2026-01-01",
            "runtime_min": 50,
            "genres": [],
            "spoken_languages": [],
            "origin_language": None,
            "production_countries": [],
            "production_companies": [],
            "directors": [],
            "creators": [],
            "writers": [],
            "actors": [],
            "episode_details": {
                "series_tmdb_id": 100,
                "series_imdb_id": "tt100",
                "series_title": "New Series",
                "season_num": season,
                "episode_num": episode,
            },
        }

    def _insert_media(self, tmdb_id, media_type, title, imdb_id=None):
        return self.conn.execute(
            """
            INSERT INTO media (tmdb_id, imdb_id, media_type, title)
            VALUES (?, ?, ?, ?)
            """,
            (tmdb_id, imdb_id, media_type, title),
        ).lastrowid

    def _insert_episode(
        self,
        series_id,
        tmdb_id,
        season_num,
        episode_num,
        title,
        imdb_id,
    ):
        episode_id = self._insert_media(tmdb_id, "episode", title, imdb_id)
        self.conn.execute(
            """
            INSERT INTO episode_details
                (media_id, series_id, season_num, episode_num)
            VALUES (?, ?, ?, ?)
            """,
            (episode_id, series_id, season_num, episode_num),
        )
        return episode_id


if __name__ == "__main__":
    unittest.main()
