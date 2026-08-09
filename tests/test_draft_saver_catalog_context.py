import os
import sqlite3
import unittest
from copy import deepcopy
from unittest.mock import patch

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
        season_poster_patcher = patch.object(
            draft_saver.tmdb,
            "get_tmdb_series_primary_season_posters",
            return_value=[],
        )
        self.fetch_season_posters = season_poster_patcher.start()
        self.addCleanup(season_poster_patcher.stop)

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
                    draft_saver.tmdb,
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
        parent_draft["posters"] = [self._media_poster("series.jpg")]
        target_draft = self._episode_draft(target, "not_interested")
        self.fetch_season_posters.return_value = [
            self._season_poster(series_tmdb_id, 1, "season-1.jpg"),
            self._season_poster(series_tmdb_id, 2, "season-2.jpg"),
            self._season_poster(series_tmdb_id, 3, "season-3.jpg"),
        ]

        with self._mock_downloads(), patch.object(
            draft_saver.media_draft_builder,
            "build_media_draft_from_tmdb_match",
            return_value=parent_draft,
        ), patch.object(
            draft_saver.tmdb,
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
        self.assertEqual(
            self._season_poster_filenames(parent_id),
            [
                (1, "season-1.jpg"),
                (2, "season-2.jpg"),
                (3, "season-3.jpg"),
            ],
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT filename FROM media_posters WHERE media_id = ?",
                (parent_id,),
            ).fetchone()["filename"],
            "series.jpg",
        )

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
            draft_saver.tmdb,
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
            draft_saver.tmdb,
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

    def test_series_saves_primary_season_posters_and_checks_parent(self):
        series_tmdb_id = 750
        series_draft = self._series_draft(series_tmdb_id, "to_watch")
        series_draft["posters"] = [self._media_poster("series.jpg")]
        series_draft["metadata"]["last_tmdb_posters_checked_at"] = (
            "premature-check"
        )
        self.fetch_season_posters.return_value = [
            self._season_poster(series_tmdb_id, 1, "season-1.jpg"),
            self._season_poster(series_tmdb_id, 2, "season-2.jpg"),
            self._season_poster(series_tmdb_id, 3, "season-3.jpg"),
        ]

        with patch.object(
            draft_saver,
            "download_missing_draft_posters",
            side_effect=self._download_every_tmdb_poster,
        ), patch.object(
            draft_saver.tmdb,
            "get_tmdb_series_episode_metadata_list",
            return_value=[],
        ), patch.object(
            draft_saver,
            "current_freshness_timestamp",
            return_value="joint-check",
        ):
            result = draft_saver.save_media_draft_with_posters(
                self.conn,
                series_draft,
                fetch_episode_imdb_ids=False,
            )

        series_id = self._media_id(series_tmdb_id, "series")
        self.assertEqual(
            self._poster_checked_at(series_id),
            "joint-check",
        )
        self.assertEqual(
            series_draft["metadata"]["last_tmdb_posters_checked_at"],
            "joint-check",
        )
        self.assertEqual(
            self._season_poster_filenames(series_id),
            [
                (1, "season-1.jpg"),
                (2, "season-2.jpg"),
                (3, "season-3.jpg"),
            ],
        )
        self.assertCountEqual(
            result["poster_downloads"]["downloaded"],
            [
                "series.jpg",
                "season-1.jpg",
                "season-2.jpg",
                "season-3.jpg",
            ],
        )
        self.assertEqual(
            set(series_draft),
            {
                "media_id",
                "metadata",
                "series_view",
                "watch_providers",
                "posters",
                "user_data",
            },
        )

    def test_series_download_failure_preserves_timestamp_and_drops_references(self):
        series_tmdb_id = 760
        existing_draft = self._series_draft(series_tmdb_id, "to_watch")
        existing_draft["metadata"]["last_tmdb_posters_checked_at"] = "old-check"
        series_id = media_repository.save_media_draft(self.conn, existing_draft)
        self.conn.execute(
            """
            INSERT INTO media_posters (
                media_id, filename, source, curation_status, is_default
            )
            VALUES (?, 'curated.jpg', 'user', 'selected', 1)
            """,
            (series_id,),
        )
        current_draft = self._series_draft(series_tmdb_id, "to_watch")
        current_draft["metadata"]["last_tmdb_posters_checked_at"] = "new-check"
        current_draft["posters"] = [self._media_poster("failed-series.jpg")]
        self.fetch_season_posters.return_value = [
            self._season_poster(series_tmdb_id, 1, "season-1.jpg"),
            self._season_poster(series_tmdb_id, 2, "failed-season.jpg"),
        ]

        def download_with_failures(media_draft, **_kwargs):
            filenames = [
                poster["filename"]
                for poster in media_draft.get("posters", [])
            ]
            failed = {
                "failed-series.jpg": "series download failed",
                "failed-season.jpg": "season download failed",
            }
            return {
                "downloaded": [
                    filename for filename in filenames if filename not in failed
                ],
                "skipped": [],
                "failed": [
                    {"filename": filename, "error": failed[filename]}
                    for filename in filenames
                    if filename in failed
                ],
            }

        with patch.object(
            draft_saver,
            "download_missing_draft_posters",
            side_effect=download_with_failures,
        ), patch.object(
            draft_saver.tmdb,
            "get_tmdb_series_episode_metadata_list",
            return_value=[],
        ):
            result = draft_saver.save_media_draft_with_posters(
                self.conn,
                current_draft,
                fetch_episode_imdb_ids=False,
            )

        self.assertEqual(self._poster_checked_at(series_id), "old-check")
        self.assertEqual(
            current_draft["metadata"]["last_tmdb_posters_checked_at"],
            "old-check",
        )
        self.assertEqual(
            self._season_poster_filenames(series_id),
            [(1, "season-1.jpg")],
        )
        saved_poster = self.conn.execute(
            """
            SELECT filename, source, curation_status, is_default
            FROM media_posters
            WHERE media_id = ?
            """,
            (series_id,),
        ).fetchone()
        self.assertEqual(
            tuple(saved_poster),
            ("curated.jpg", "user", "selected", 1),
        )
        self.assertCountEqual(
            [failure["filename"] for failure in result["poster_downloads"]["failed"]],
            ["failed-series.jpg", "failed-season.jpg"],
        )

    def test_direct_episode_checks_only_parent_and_preserves_episode_timestamp(self):
        series_tmdb_id = 770
        parent_draft = self._series_draft(series_tmdb_id, "to_watch")
        parent_draft["metadata"]["last_tmdb_posters_checked_at"] = "old-parent"
        parent_id = media_repository.save_media_draft(self.conn, parent_draft)
        target = self._episode_metadata(series_tmdb_id, 1, 1)
        target["last_tmdb_posters_checked_at"] = "episode-fetch-check"
        target_draft = self._episode_draft(target, "to_watch")
        target_draft["posters"] = [self._media_poster("failed-episode.jpg")]
        self.fetch_season_posters.return_value = [
            self._season_poster(series_tmdb_id, 1, "season-1.jpg"),
            self._season_poster(series_tmdb_id, 2, "season-2.jpg"),
        ]

        def download_with_episode_failure(media_draft, **_kwargs):
            filenames = [
                poster["filename"]
                for poster in media_draft.get("posters", [])
            ]
            return {
                "downloaded": [
                    filename
                    for filename in filenames
                    if filename != "failed-episode.jpg"
                ],
                "skipped": [],
                "failed": (
                    [{"filename": "failed-episode.jpg", "error": "episode failed"}]
                    if "failed-episode.jpg" in filenames
                    else []
                ),
            }

        with patch.object(
            draft_saver,
            "download_missing_draft_posters",
            side_effect=download_with_episode_failure,
        ), patch.object(
            draft_saver.tmdb,
            "get_tmdb_series_episode_metadata_list",
            return_value=[target],
        ), patch.object(
            draft_saver,
            "current_freshness_timestamp",
            return_value="new-parent-check",
        ):
            result = draft_saver.save_media_draft_with_posters(
                self.conn,
                target_draft,
                fetch_episode_imdb_ids=False,
            )

        episode_id = self._media_id(target["tmdb_id"], "episode")
        self.assertEqual(self._poster_checked_at(parent_id), "new-parent-check")
        self.assertIsNone(self._poster_checked_at(episode_id))
        self.assertIsNone(
            target_draft["metadata"]["last_tmdb_posters_checked_at"]
        )
        self.assertEqual(
            self._season_poster_filenames(parent_id),
            [(1, "season-1.jpg"), (2, "season-2.jpg")],
        )
        self.assertEqual(
            [failure["filename"] for failure in result["poster_downloads"]["failed"]],
            ["failed-episode.jpg"],
        )
        self.assertEqual(
            set(target_draft),
            {
                "media_id",
                "metadata",
                "watch_providers",
                "posters",
                "user_data",
            },
        )

    def test_direct_episode_keeps_canonical_season_poster_collected_for_parent(self):
        series_tmdb_id = 780
        parent_id = media_repository.save_media_draft(
            self.conn,
            self._series_draft(series_tmdb_id, "to_watch"),
        )
        target = self._episode_metadata(series_tmdb_id, 1, 1)
        target_draft = self._episode_draft(target, "to_watch")
        target_draft["posters"] = [
            self._season_poster(
                series_tmdb_id,
                1,
                "episode-season-candidate.jpg",
            )
        ]
        self.fetch_season_posters.return_value = [
            self._season_poster(
                series_tmdb_id,
                1,
                "canonical-season.jpg",
            )
        ]

        with patch.object(
            draft_saver,
            "download_missing_draft_posters",
            side_effect=self._download_every_tmdb_poster,
        ), patch.object(
            draft_saver.tmdb,
            "get_tmdb_series_episode_metadata_list",
            return_value=[target],
        ):
            draft_saver.save_media_draft_with_posters(
                self.conn,
                target_draft,
                fetch_episode_imdb_ids=False,
            )

        self.assertEqual(
            self._season_poster_filenames(parent_id),
            [(1, "canonical-season.jpg")],
        )

    def test_failed_download_filter_preserves_user_and_other_posters(self):
        media_draft = {
            "posters": [
                self._media_poster("failed.jpg"),
                {
                    **self._media_poster("failed.jpg"),
                    "source": "user",
                },
                {
                    **self._media_poster("other.jpg"),
                    "source": "other",
                },
            ],
        }

        draft_saver._remove_failed_tmdb_poster_references(
            media_draft,
            {
                "downloaded": [],
                "skipped": [],
                "failed": [{"filename": "failed.jpg", "error": "network"}],
            },
        )

        self.assertEqual(
            [(poster["source"], poster["filename"]) for poster in media_draft["posters"]],
            [("user", "failed.jpg"), ("other", "other.jpg")],
        )

    def test_existing_series_save_is_local_and_skips_episode_catalog(self):
        baseline = self._series_draft(800, "to_watch")
        media_id = media_repository.save_media_draft(self.conn, baseline)
        current = deepcopy(baseline)
        current["user_data"]["impression"] = "very_good"

        with patch.object(
            draft_saver.tmdb,
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
            draft_saver.tmdb,
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
            side_effect=lambda *_args, **_kwargs: deepcopy(EMPTY_DOWNLOADS),
        )

    def _media_poster(self, filename):
        return {
            "scope": "media",
            "filename": filename,
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False,
        }

    def _season_poster(self, series_tmdb_id, season_num, filename):
        return {
            "scope": "season",
            "filename": filename,
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False,
            "series_tmdb_id": series_tmdb_id,
            "season_num": season_num,
        }

    def _download_every_tmdb_poster(self, media_draft, **_kwargs):
        return {
            "downloaded": [
                poster["filename"]
                for poster in media_draft.get("posters", [])
                if poster.get("source", "tmdb") == "tmdb"
            ],
            "skipped": [],
            "failed": [],
        }

    def _poster_checked_at(self, media_id):
        return self.conn.execute(
            "SELECT last_tmdb_posters_checked_at FROM media WHERE id = ?",
            (media_id,),
        ).fetchone()["last_tmdb_posters_checked_at"]

    def _season_poster_filenames(self, series_id):
        return [
            (row["season_num"], row["filename"])
            for row in self.conn.execute(
                """
                SELECT season_num, filename
                FROM season_posters
                WHERE series_id = ?
                ORDER BY season_num, filename
                """,
                (series_id,),
            ).fetchall()
        ]

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
