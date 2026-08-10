import unittest
from datetime import date

from app.media_user_data.watch_history import (
    apply_watch_entry_result,
    is_episode_available,
    validate_watch_dates,
    watched_episode_keys,
)
from app.media_user_data.watch_history_formatters import (
    build_watch_history_display_entries,
)


class WatchHistoryEditorTests(unittest.TestCase):
    def test_validate_watch_dates_requires_iso_format(self):
        self.assertTrue(validate_watch_dates("", "")["is_valid"])
        self.assertTrue(validate_watch_dates("2026-05-01", "2026-05-31")["is_valid"])
        self.assertFalse(validate_watch_dates("2026/05/01", "")["is_valid"])
        self.assertFalse(validate_watch_dates("2026-05-31", "2026-05-01")["is_valid"])

    def test_validate_watch_dates_reports_stable_error_types(self):
        cases = (
            (
                "empty dates",
                "",
                "",
                {
                    "is_valid": True,
                    "date_earliest": None,
                    "date_latest": None,
                    "error": None,
                    "error_type": None,
                },
            ),
            (
                "valid range",
                "2026-05-01",
                "2026-05-31",
                {
                    "is_valid": True,
                    "date_earliest": "2026-05-01",
                    "date_latest": "2026-05-31",
                    "error": None,
                    "error_type": None,
                },
            ),
            (
                "invalid earliest format",
                "2026/05/01",
                "",
                {
                    "is_valid": False,
                    "date_earliest": None,
                    "date_latest": None,
                    "error": "Use YYYY-MM-DD.",
                    "error_type": "invalid_format",
                },
            ),
            (
                "invalid latest format",
                "",
                "May 31, 2026",
                {
                    "is_valid": False,
                    "date_earliest": None,
                    "date_latest": None,
                    "error": "Use YYYY-MM-DD.",
                    "error_type": "invalid_format",
                },
            ),
            (
                "latest before earliest",
                "2026-05-31",
                "2026-05-01",
                {
                    "is_valid": False,
                    "date_earliest": "2026-05-31",
                    "date_latest": "2026-05-01",
                    "error": "Latest date must be on or after earliest date.",
                    "error_type": "invalid_range",
                },
            ),
        )

        for name, date_earliest, date_latest, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    validate_watch_dates(date_earliest, date_latest),
                    expected,
                )

    def test_episode_availability_requires_released_iso_date(self):
        today = date(2026, 7, 13)

        self.assertTrue(
            is_episode_available({"release_date": "2026-07-12"}, today=today)
        )
        self.assertTrue(
            is_episode_available({"release_date": "2026-07-13"}, today=today)
        )
        self.assertFalse(
            is_episode_available({"release_date": "2026-07-14"}, today=today)
        )

        for release_date in (None, "", "2026-7-13", "not-a-date", date(2026, 7, 13)):
            with self.subTest(release_date=release_date):
                self.assertFalse(
                    is_episode_available(
                        {"release_date": release_date},
                        today=today,
                    )
                )

    def test_add_edit_delete_movie_watch_entry(self):
        media_draft = {
            "metadata": {
                "media_type": "movie",
                "release_date": "2020-01-01",
            },
            "user_data": {"watch_history": []},
        }

        apply_watch_entry_result(media_draft, None, {
            "action": "save",
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
            "selected_episodes": [],
        })
        self.assertEqual(
            media_draft["user_data"]["watch_history"][0]["date_earliest"],
            "2026-05-01",
        )

        entry = build_watch_history_display_entries(media_draft)[0]
        apply_watch_entry_result(media_draft, entry, {
            "action": "save",
            "date_earliest": "2026-05-02",
            "date_latest": "2026-05-02",
            "selected_episodes": [],
        })
        self.assertEqual(len(media_draft["user_data"]["watch_history"]), 1)
        self.assertEqual(
            media_draft["user_data"]["watch_history"][0]["date_earliest"],
            "2026-05-02",
        )

        entry = build_watch_history_display_entries(media_draft)[0]
        apply_watch_entry_result(media_draft, entry, {"action": "delete"})
        self.assertEqual(media_draft["user_data"]["watch_history"], [])

    def test_sorted_movie_entry_keeps_its_original_index_when_edited(self):
        media_draft = {
            "metadata": {
                "media_type": "movie",
                "release_date": "2020-01-01",
            },
            "user_data": {
                "watch_history": [
                    {
                        "id": 1,
                        "date_earliest": "2024-01-01",
                        "date_latest": "2024-01-01",
                        "created_at": "2026-01-01 10:00:00",
                    },
                    {
                        "id": 2,
                        "date_earliest": "2025-01-01",
                        "date_latest": "2025-01-01",
                        "created_at": "2025-01-01 10:00:00",
                    },
                ],
            },
        }

        newest_entry = build_watch_history_display_entries(media_draft)[0]
        self.assertEqual(newest_entry["watch_history_id"], 2)
        self.assertEqual(newest_entry["watch_history_index"], 1)

        apply_watch_entry_result(media_draft, newest_entry, {
            "action": "save",
            "date_earliest": "2025-02-01",
            "date_latest": "2025-02-01",
            "selected_episodes": [],
        })

        self.assertEqual(
            media_draft["user_data"]["watch_history"][0]["date_earliest"],
            "2024-01-01",
        )
        self.assertEqual(
            media_draft["user_data"]["watch_history"][1]["date_earliest"],
            "2025-02-01",
        )

    def test_series_entry_can_move_between_series_and_episode_history(self):
        media_draft = {
            "media_id": 10,
            "metadata": {
                "media_type": "series",
                "release_date": "2026-01-01",
            },
            "user_data": {"watch_history": []},
            "series_view": {
                "summary": {"first_air_date": "2026-01-01"},
                "episodes": [
                    _episode(10, 101, 1, 1),
                    _episode(10, 102, 1, 2),
                    _episode(10, 103, 1, 3),
                ],
                "episode_watch_history": [],
            },
        }

        apply_watch_entry_result(media_draft, None, {
            "action": "save",
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
            "selected_episodes": [
                _episode(10, 101, 1, 1),
                _episode(10, 102, 1, 2),
            ],
        })
        self.assertEqual(media_draft["user_data"]["watch_history"], [])
        self.assertEqual(
            _episode_keys(media_draft["series_view"]["episode_watch_history"]),
            [(1, 1), (1, 2)],
        )

        entry = build_watch_history_display_entries(media_draft)[0]
        apply_watch_entry_result(media_draft, entry, {
            "action": "save",
            "date_earliest": "2026-05-02",
            "date_latest": "2026-05-02",
            "selected_episodes": [
                _episode(10, 102, 1, 2),
                _episode(10, 103, 1, 3),
            ],
        })
        rows = media_draft["series_view"]["episode_watch_history"]
        self.assertEqual(_episode_keys(rows), [(1, 2), (1, 3)])
        self.assertEqual({row["date_earliest"] for row in rows}, {"2026-05-02"})

        entry = build_watch_history_display_entries(media_draft)[0]
        apply_watch_entry_result(media_draft, entry, {
            "action": "save",
            "date_earliest": "2026-05-03",
            "date_latest": "2026-05-03",
            "selected_episodes": [],
        })
        self.assertEqual(media_draft["series_view"]["episode_watch_history"], [])
        self.assertEqual(len(media_draft["user_data"]["watch_history"]), 1)

        entry = build_watch_history_display_entries(media_draft)[0]
        apply_watch_entry_result(media_draft, entry, {
            "action": "save",
            "date_earliest": "2026-05-04",
            "date_latest": "2026-05-04",
            "selected_episodes": [_episode(10, 101, 1, 1)],
        })
        self.assertEqual(media_draft["user_data"]["watch_history"], [])
        self.assertEqual(
            _episode_keys(media_draft["series_view"]["episode_watch_history"]),
            [(1, 1)],
        )

        entry = build_watch_history_display_entries(media_draft)[0]
        apply_watch_entry_result(media_draft, entry, {"action": "delete"})
        self.assertEqual(media_draft["series_view"]["episode_watch_history"], [])

    def test_watched_episode_keys_can_exclude_current_entry(self):
        media_draft = {
            "series_view": {
                "episode_watch_history": [
                    {
                        "watch_history_id": 1,
                        "season_num": 1,
                        "episode_num": 1,
                        "date_earliest": "2026-05-01",
                        "date_latest": "2026-05-01",
                    },
                    {
                        "watch_history_id": 2,
                        "season_num": 1,
                        "episode_num": 2,
                        "date_earliest": "2026-05-02",
                        "date_latest": "2026-05-02",
                    },
                ],
            },
        }
        entry = {
            "watch_history_ids": [1],
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
            "episodes": [
                {
                    "season_num": 1,
                    "episode_num": 1,
                },
            ],
        }

        self.assertEqual(watched_episode_keys(media_draft, entry), {(1, 2)})


def _episode(series_id, episode_id, season_num, episode_num):
    return {
        "series_id": series_id,
        "episode_id": episode_id,
        "tmdb_id": 1000 + episode_id,
        "season_num": season_num,
        "episode_num": episode_num,
        "title": f"Episode {episode_num}",
        "release_date": None,
    }


def _episode_keys(rows):
    return sorted(
        (row["season_num"], row["episode_num"])
        for row in rows
    )


if __name__ == "__main__":
    unittest.main()
