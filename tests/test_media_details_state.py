import unittest

from app.media_draft import (
    apply_inserted_ids_to_draft,
    merge_metadata_refresh,
)


class MediaDetailsStateTests(unittest.TestCase):
    def test_applies_inserted_ids_only_after_save_result(self):
        draft = {
            "user_data": {
                "watch_history": [{"draft_id": "media-new"}],
                "notes": [{"draft_id": "note-new", "note": "hello"}],
            },
            "series_view": {
                "episode_watch_history": [{"draft_id": "episode-new"}],
            },
        }
        result = {
            "inserted_ids_by_draft_id": {
                "media_watch_history": {"media-new": 10},
                "notes": {"note-new": 20},
                "series_episode_watch_history": {"episode-new": 30},
            },
        }

        apply_inserted_ids_to_draft(draft, result)

        self.assertEqual(draft["user_data"]["watch_history"][0], {"id": 10})
        self.assertEqual(
            draft["user_data"]["notes"][0],
            {"id": 20, "note": "hello"},
        )
        self.assertEqual(
            draft["series_view"]["episode_watch_history"][0],
            {"watch_history_id": 30},
        )

    def test_refresh_merge_preserves_user_edits_and_renumbers_history(self):
        draft = {
            "media_id": 1,
            "metadata": {
                "media_type": "series",
                "title": "Old",
                "last_tmdb_posters_checked_at": "poster-time",
                "last_tmdb_watch_providers_checked_at": "provider-time",
            },
            "user_data": {
                "impression": "very_good",
                "watch_history": [{"draft_id": "series-watch"}],
            },
            "series_view": {
                "summary": {"episode_count": 1},
                "episodes": [{"episode_id": 11, "tmdb_id": 101}],
                "episode_watch_history": [{
                    "episode_id": 11,
                    "tmdb_id": 101,
                    "season_num": 1,
                    "episode_num": 1,
                    "draft_id": "episode-watch",
                    "date_earliest": "2026-01-01",
                }],
            },
        }
        payload = {
            "snapshot": {"metadata": {"media_type": "series"}},
            "refresh_result": {
                "metadata": {
                    "media_type": "series",
                    "title": "Updated",
                    "last_tmdb_metadata_checked_at": "metadata-time",
                },
                "series_catalog": {
                    "summary": {"episode_count": 2},
                    "episodes": [
                        {
                            "series_id": 1,
                            "episode_id": 11,
                            "tmdb_id": 101,
                            "season_num": 2,
                            "episode_num": 3,
                            "title": "Moved",
                        },
                        {
                            "series_id": 1,
                            "episode_id": 12,
                            "tmdb_id": 102,
                            "season_num": 2,
                            "episode_num": 4,
                            "title": "New",
                        },
                    ],
                },
            },
        }

        merged = merge_metadata_refresh(draft, payload)

        self.assertEqual(merged["metadata"]["title"], "Updated")
        self.assertEqual(
            merged["metadata"]["last_tmdb_posters_checked_at"],
            "poster-time",
        )
        self.assertEqual(merged["user_data"], draft["user_data"])
        self.assertEqual(len(merged["series_view"]["episodes"]), 2)
        history = merged["series_view"]["episode_watch_history"][0]
        self.assertEqual((history["season_num"], history["episode_num"]), (2, 3))
        self.assertEqual(history["draft_id"], "episode-watch")

    def test_new_series_snapshot_builds_episode_grid_without_db_ids(self):
        draft = {
            "media_id": None,
            "metadata": {"media_type": "series"},
            "user_data": {"impression": "good"},
            "series_view": {"episode_watch_history": []},
        }
        payload = {
            "snapshot": {
                "metadata": {"media_type": "series", "title": "Series"},
                "series_summary": {"episode_count": 1},
                "regular_episodes": [{
                    "tmdb_id": 501,
                    "title": "Pilot",
                    "release_date": "2026-01-01",
                    "episode_details": {"season_num": 1, "episode_num": 1},
                }],
            },
            "refresh_result": None,
        }

        merged = merge_metadata_refresh(draft, payload)

        self.assertEqual(merged["user_data"], {"impression": "good"})
        self.assertEqual(
            merged["series_view"]["episodes"][0],
            {
                "series_id": None,
                "episode_id": None,
                "tmdb_id": 501,
                "season_num": 1,
                "episode_num": 1,
                "title": "Pilot",
                "release_date": "2026-01-01",
            },
        )

    def test_new_series_refresh_rejects_orphaned_unsaved_episode_entry(self):
        draft = {
            "media_id": None,
            "metadata": {"media_type": "series"},
            "user_data": {},
            "series_view": {
                "episodes": [{
                    "tmdb_id": 700,
                    "season_num": 1,
                    "episode_num": 1,
                }],
                "episode_watch_history": [{
                    "draft_id": "watch-700",
                    "tmdb_id": 700,
                    "season_num": 1,
                    "episode_num": 1,
                }],
            },
        }
        payload = {
            "snapshot": {
                "metadata": {"media_type": "series", "title": "Series"},
                "series_summary": {"episode_count": 0},
                "regular_episodes": [],
            },
            "refresh_result": None,
        }

        with self.assertRaisesRegex(ValueError, "orphan"):
            merge_metadata_refresh(draft, payload)


if __name__ == "__main__":
    unittest.main()
