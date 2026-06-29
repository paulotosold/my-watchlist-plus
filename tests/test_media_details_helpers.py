import os
import unittest

os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from app.media_details_formatters import (
    build_metadata_display_rows,
    build_series_watch_history_lines,
    format_code_or_name_list,
    format_date_range,
    format_people_with_jobs,
    format_runtime_minutes,
    format_watch_provider_checked_at,
    format_watch_history_entry,
    group_watch_providers,
)


class MediaDetailsHelperTests(unittest.TestCase):
    def test_format_runtime_minutes(self):
        self.assertEqual(format_runtime_minutes(157), "2h 37min")
        self.assertEqual(format_runtime_minutes(31), "31min")
        self.assertEqual(format_runtime_minutes(60), "1h")
        self.assertEqual(format_runtime_minutes(31, approximate=True), "~31min")
        self.assertIsNone(format_runtime_minutes(None))

    def test_format_metadata_lists(self):
        self.assertEqual(
            format_code_or_name_list(
                [{"code": "en", "name": "English"}, {"code": "ja", "name": "Japanese"}],
                "code",
            ),
            "en, ja",
        )
        self.assertEqual(
            format_people_with_jobs([
                {"name": "Drew Goddard", "job": "Screenplay"},
                {"name": "Andy Weir"},
            ]),
            "Drew Goddard (Screenplay), Andy Weir",
        )

    def test_metadata_rows_show_none_for_empty_values(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 1,
                "imdb_id": None,
                "media_type": "movie",
                "title": "Example",
                "original_title": None,
                "production_status": None,
                "release_date": None,
                "runtime_min": None,
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "directors": [],
                "writers": [],
                "actors": [],
            },
            "series_view": None,
        })
        row_texts = [row["text"] for row in rows]

        self.assertIn("IMDb ID: None", row_texts)
        self.assertIn("Original Title: None", row_texts)
        self.assertIn("Runtime: None", row_texts)
        self.assertIn("Genres: None", row_texts)
        self.assertNotIn("Season Count: None", row_texts)

    def test_imdb_row_has_external_link_marker_and_tooltip(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 1,
                "imdb_id": "tt0095327",
                "media_type": "movie",
                "title": "Example",
                "original_title": "Example",
                "production_status": None,
                "release_date": None,
                "runtime_min": None,
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "directors": [],
                "writers": [],
                "actors": [],
            },
            "series_view": None,
        })
        imdb_row = next(row for row in rows if row["text"].startswith("IMDb ID:"))

        self.assertIn("tt0095327 ↗", imdb_row["text"])
        self.assertEqual(imdb_row["tooltip"], "Open on IMDb")

    def test_series_omits_writers_and_uses_main_cast(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 1,
                "imdb_id": None,
                "media_type": "series",
                "title": "Example",
                "original_title": "Example",
                "production_status": None,
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "creators": [],
                "writers": [{"name": "Writer"}],
                "actors": [],
            },
            "series_view": {"summary": {}},
        })
        row_texts = [row["text"] for row in rows]

        self.assertNotIn("Writers: Writer", row_texts)
        self.assertIn("Main Cast: None", row_texts)

    def test_movie_uses_cast_label(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 1,
                "imdb_id": None,
                "media_type": "movie",
                "title": "Example",
                "original_title": "Example",
                "production_status": None,
                "release_date": None,
                "runtime_min": None,
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "directors": [],
                "writers": [],
                "actors": [],
            },
            "series_view": None,
        })
        row_texts = [row["text"] for row in rows]

        self.assertIn("Cast: None", row_texts)
        self.assertNotIn("Main Cast: None", row_texts)

    def test_format_watch_provider_checked_at_missing(self):
        self.assertIsNone(format_watch_provider_checked_at([]))
        self.assertIsNone(format_watch_provider_checked_at([
            {"provider_name": "Netflix"},
        ]))

    def test_format_watch_provider_checked_at_uses_latest_timestamp(self):
        self.assertEqual(
            format_watch_provider_checked_at([
                {
                    "provider_name": "Netflix",
                    "checked_at": "2026-06-29 11:53:44",
                },
                {
                    "provider_name": "Apple TV",
                    "checked_at": "2026-06-29 12:01:05",
                },
            ]),
            "29 Jun 2026, 12:01",
        )

    def test_format_watch_provider_checked_at_with_identical_timestamps(self):
        self.assertEqual(
            format_watch_provider_checked_at([
                {
                    "provider_name": "Netflix",
                    "checked_at": "2026-06-29 11:53:44",
                },
                {
                    "provider_name": "Disney Plus",
                    "checked_at": "2026-06-29 11:53:44",
                },
            ]),
            "29 Jun 2026, 11:53",
        )

    def test_format_watch_provider_checked_at_ignores_invalid_values(self):
        self.assertEqual(
            format_watch_provider_checked_at([
                {"provider_name": "Broken", "checked_at": "not-a-date"},
                {"provider_name": "Valid", "checked_at": "2026-06-29 11:53:44"},
            ]),
            "29 Jun 2026, 11:53",
        )
        self.assertIsNone(format_watch_provider_checked_at([
            {"provider_name": "Broken", "checked_at": "not-a-date"},
        ]))

    def test_group_watch_providers_still_groups_by_access_type(self):
        self.assertEqual(
            group_watch_providers([
                {
                    "provider_name": "Netflix",
                    "access_type": "flatrate",
                    "checked_at": "2026-06-29 11:53:44",
                },
                {
                    "provider_name": "Apple TV",
                    "access_type": "rent",
                    "checked_at": "2026-06-29 11:53:44",
                },
                {
                    "provider_name": "Apple TV",
                    "access_type": "rent",
                    "checked_at": "2026-06-29 11:53:44",
                },
            ]),
            {
                "flatrate": ["Netflix"],
                "buy": [],
                "rent": ["Apple TV"],
            },
        )

    def test_format_watch_history_date_ranges(self):
        self.assertEqual(
            format_watch_history_entry({
                "date_earliest": "2022-06-15",
                "date_latest": "2022-06-15",
            }),
            "15 Jun 2022, Wed",
        )
        self.assertEqual(
            format_watch_history_entry({
                "date_earliest": "2022-06-01",
                "date_latest": "2022-06-20",
            }),
            "Jun 2022",
        )
        self.assertEqual(
            format_watch_history_entry({
                "date_earliest": "2022-03-01",
                "date_latest": "2022-06-20",
            }),
            "2022",
        )
        self.assertEqual(
            format_watch_history_entry({
                "date_earliest": "2020-03-01",
                "date_latest": "2022-06-20",
            }),
            "2020-2022",
        )

    def test_format_watch_history_fallbacks(self):
        self.assertEqual(
            format_watch_history_entry(
                {
                    "date_earliest": None,
                    "date_latest": None,
                    "created_at": "2025-06-01 10:30:00",
                },
                release_date="2000-01-01",
            ),
            "Probably 2000-2025",
        )

    def test_series_episode_watch_history_grouping(self):
        media_draft = {
            "metadata": {
                "media_type": "series",
                "release_date": "2022-06-01",
            },
            "user_data": {"watch_history": []},
            "series_view": {
                "summary": {"first_air_date": "2022-06-01"},
                "episode_watch_history": [
                    {
                        "watch_history_id": 1,
                        "date_earliest": "2022-06-15",
                        "date_latest": "2022-06-15",
                        "created_at": "2022-06-16 10:00:00",
                        "season_num": 1,
                        "episode_num": 1,
                    },
                    {
                        "watch_history_id": 1,
                        "date_earliest": "2022-06-15",
                        "date_latest": "2022-06-15",
                        "created_at": "2022-06-16 10:00:00",
                        "season_num": 1,
                        "episode_num": 2,
                    },
                    {
                        "watch_history_id": 1,
                        "date_earliest": "2022-06-15",
                        "date_latest": "2022-06-15",
                        "created_at": "2022-06-16 10:00:00",
                        "season_num": 1,
                        "episode_num": 3,
                    },
                ],
            },
        }

        self.assertEqual(
            build_series_watch_history_lines(media_draft),
            ["15 Jun 2022, Wed · S1:E1-3"],
        )


if __name__ == "__main__":
    unittest.main()
