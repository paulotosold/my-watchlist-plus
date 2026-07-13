import os
import sqlite3
import unittest
from copy import deepcopy
from unittest.mock import patch

os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import app.draft_saver as draft_saver
import app.media_repository as media_repository
from db.connection import apply_database_schema


EMPTY_DOWNLOADS = {
    "downloaded": [],
    "skipped": [],
    "failed": [],
}


class DraftSaverCatalogContextTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_every_series_state_materializes_neutral_episode_catalog(self):
        for index, watch_state in enumerate(
            (None, "to_watch", "watched", "not_interested", "dropped"),
            start=1,
        ):
            with self.subTest(watch_state=watch_state):
                series_tmdb_id = index * 100
                series_draft = self._series_draft(series_tmdb_id, watch_state)
                episodes = [
                    self._episode_metadata(series_tmdb_id, 1, 1),
                    self._episode_metadata(series_tmdb_id, 1, 2),
                ]

                with self._mock_downloads(), patch.object(
                    draft_saver.tmdb_fetcher,
                    "get_tmdb_series_episode_metadata_list",
                    return_value=episodes,
                ):
                    result = draft_saver.save_media_draft_with_posters(
                        self.conn,
                        series_draft,
                        fetch_episode_imdb_ids=False,
                    )

                series_id = self._media_id(series_tmdb_id, "series")
                episode_ids = [
                    self._media_id(item["tmdb_id"], "episode")
                    for item in episodes
                ]
                if watch_state is None:
                    self.assertIsNone(self._state_row(series_id))
                else:
                    self.assertEqual(self._watch_state(series_id), watch_state)
                self.assertEqual(
                    [self._watch_state(episode_id) for episode_id in episode_ids],
                    [None, None],
                )
                self.assertEqual(result["episode_seed_count"], 2)
                self.assertTrue(result["series_completed"])

    def test_direct_episode_creates_neutral_parent_and_siblings(self):
        series_tmdb_id = 500
        target = self._episode_metadata(series_tmdb_id, 1, 1)
        sibling = self._episode_metadata(series_tmdb_id, 1, 2)
        parent_draft = self._series_draft(series_tmdb_id, "to_watch")
        target_draft = self._episode_draft(target, "not_interested")

        with self._mock_downloads(), patch.object(
            draft_saver.media_draft_builder,
            "build_media_draft_from_tmdb_match",
            return_value=parent_draft,
        ), patch.object(
            draft_saver.tmdb_fetcher,
            "get_tmdb_series_episode_metadata_list",
            return_value=[target, sibling],
        ):
            result = draft_saver.save_media_draft_with_posters(
                self.conn,
                target_draft,
                fetch_episode_imdb_ids=False,
            )

        parent_id = self._media_id(series_tmdb_id, "series")
        target_id = self._media_id(target["tmdb_id"], "episode")
        sibling_id = self._media_id(sibling["tmdb_id"], "episode")

        self.assertIsNone(self._state_row(parent_id))
        self.assertEqual(self._watch_state(target_id), "not_interested")
        self.assertIsNone(self._state_row(sibling_id))
        self.assertEqual(result["media_id"], target_id)
        self.assertEqual(result["saved_media_type"], "episode")
        self.assertTrue(result["saved_original_episode"])
        self.assertTrue(result["series_created"])

    def test_direct_episode_preserves_existing_parent_override(self):
        series_tmdb_id = 600
        parent_draft = self._series_draft(series_tmdb_id, "dropped")
        parent_id = media_repository.save_media_draft(self.conn, parent_draft)
        target = self._episode_metadata(series_tmdb_id, 2, 3)
        sibling = self._episode_metadata(series_tmdb_id, 2, 4)
        target_draft = self._episode_draft(target, "to_watch")

        with self._mock_downloads(), patch.object(
            draft_saver.media_draft_builder,
            "build_media_draft_from_tmdb_match",
        ) as build_parent, patch.object(
            draft_saver.tmdb_fetcher,
            "get_tmdb_series_episode_metadata_list",
            return_value=[target, sibling],
        ):
            result = draft_saver.save_media_draft_with_posters(
                self.conn,
                target_draft,
                fetch_episode_imdb_ids=False,
            )

        build_parent.assert_not_called()
        self.assertEqual(self._watch_state(parent_id), "dropped")
        self.assertEqual(
            self._watch_state(self._media_id(target["tmdb_id"], "episode")),
            "to_watch",
        )
        self.assertIsNone(
            self._state_row(self._media_id(sibling["tmdb_id"], "episode")),
        )
        self.assertFalse(result["series_created"])

    def test_new_series_reuses_metadata_refresh_snapshot(self):
        series_tmdb_id = 700
        series_draft = self._series_draft(series_tmdb_id, "to_watch")
        episodes = [
            self._episode_metadata(series_tmdb_id, 1, 1),
            self._episode_metadata(series_tmdb_id, 1, 2),
        ]
        series_draft["_metadata_refresh_snapshot"] = {
            "media_type": "series",
            "tmdb_id": series_tmdb_id,
            "regular_episodes": episodes,
        }

        with self._mock_downloads(), patch.object(
            draft_saver.tmdb_fetcher,
            "get_tmdb_series_episode_metadata_list",
        ) as fetch_episodes:
            result = draft_saver.save_media_draft_with_posters(
                self.conn,
                series_draft,
            )

        fetch_episodes.assert_not_called()
        self.assertEqual(result["episode_seed_count"], 2)
        self.assertIsNotNone(self._media_id(episodes[0]["tmdb_id"], "episode"))
        self.assertIsNotNone(self._media_id(episodes[1]["tmdb_id"], "episode"))

    def test_existing_series_save_is_local_and_skips_episode_catalog(self):
        baseline = self._series_draft(800, "to_watch")
        media_id = media_repository.save_media_draft(self.conn, baseline)
        current = deepcopy(baseline)
        current["user_data"]["impression"] = "very_good"

        with patch.object(
            draft_saver.tmdb_fetcher,
            "get_tmdb_series_episode_metadata_list",
        ) as fetch_episodes, patch.object(
            draft_saver,
            "download_missing_draft_posters",
        ) as download_posters:
            result = draft_saver.save_existing_media_changes(
                self.conn,
                baseline,
                current,
            )

        fetch_episodes.assert_not_called()
        download_posters.assert_not_called()
        self.assertEqual(result["media_id"], media_id)
        self.assertEqual(
            self.conn.execute(
                "SELECT impression FROM media_state WHERE media_id = ?",
                (media_id,),
            ).fetchone()["impression"],
            "very_good",
        )

    def test_existing_episode_save_does_not_seed_parent_or_siblings(self):
        metadata = self._episode_metadata(900, 1, 1)
        baseline = self._episode_draft(metadata, "to_watch")
        media_id = media_repository.save_media_draft(self.conn, baseline)
        current = deepcopy(baseline)
        current["user_data"]["impression"] = "good"

        with patch.object(
            draft_saver.tmdb_fetcher,
            "get_tmdb_series_episode_metadata_list",
        ) as fetch_episodes, patch.object(
            draft_saver.media_draft_builder,
            "build_media_draft_from_tmdb_match",
        ) as build_parent:
            result = draft_saver.save_existing_media_changes(
                self.conn,
                baseline,
                current,
            )

        fetch_episodes.assert_not_called()
        build_parent.assert_not_called()
        self.assertEqual(result["media_id"], media_id)

    def _series_draft(self, tmdb_id, watch_state):
        return {
            "media_id": None,
            "metadata": {
                "tmdb_id": tmdb_id,
                "media_type": "series",
                "title": f"Series {tmdb_id}",
            },
            "watch_providers": [],
            "posters": [],
            "user_data": self._user_data(watch_state),
            "series_view": {},
        }

    def _episode_metadata(self, series_tmdb_id, season_num, episode_num):
        return {
            "tmdb_id": series_tmdb_id + season_num * 10 + episode_num,
            "media_type": "episode",
            "title": f"Episode {episode_num}",
            "episode_details": {
                "series_tmdb_id": series_tmdb_id,
                "series_title": f"Series {series_tmdb_id}",
                "season_num": season_num,
                "episode_num": episode_num,
            },
        }

    def _episode_draft(self, metadata, watch_state):
        return {
            "media_id": None,
            "metadata": metadata,
            "watch_providers": [],
            "posters": [],
            "user_data": self._user_data(watch_state),
        }

    def _user_data(self, watch_state):
        return {
            "watch_state": watch_state,
            "impression": None,
            "is_collection_pick": None,
            "watch_history": [],
            "notes": [],
            "lists": [],
        }

    def _mock_downloads(self):
        return patch.object(
            draft_saver,
            "download_missing_draft_posters",
            return_value=EMPTY_DOWNLOADS,
        )

    def _media_id(self, tmdb_id, media_type):
        row = self.conn.execute(
            """
            SELECT id
            FROM media
            WHERE tmdb_id = ?
              AND media_type = ?
            """,
            (tmdb_id, media_type),
        ).fetchone()
        self.assertIsNotNone(row)
        return row["id"]

    def _state_row(self, media_id):
        return self.conn.execute(
            "SELECT * FROM media_state WHERE media_id = ?",
            (media_id,),
        ).fetchone()

    def _watch_state(self, media_id):
        row = self._state_row(media_id)
        return None if row is None else row["watch_state"]


if __name__ == "__main__":
    unittest.main()
