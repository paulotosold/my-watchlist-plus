import os
import unittest
from datetime import date, datetime

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from app.media_details.formatters import (
    build_metadata_display_rows,
    format_code_or_name_list,
    format_metadata_date,
    format_people_with_jobs,
    format_runtime_minutes,
    format_watch_provider_checked_at,
    group_watch_providers,
)
from app.media_user_data.watch_history_formatters import (
    build_series_watch_history_lines,
    build_watch_history_display_entries,
    format_date_range,
    format_watch_history_entry,
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
            format_code_or_name_list(
                [
                    {"code": "en", "name": "English"},
                    {"code": "es", "name": "Spanish"},
                ],
                "name",
            ),
            "English, Spanish",
        )
        self.assertEqual(
            format_people_with_jobs([
                {"name": "Drew Goddard", "job": "Screenplay"},
                {"name": "Andy Weir"},
            ]),
            "Drew Goddard (Screenplay), Andy Weir",
        )

    def test_format_metadata_date_matches_watch_history_style(self):
        self.assertEqual(
            format_metadata_date("2026-07-17"),
            "17 Jul 2026, Fri",
        )
        self.assertEqual(format_metadata_date("invalid"), "invalid")
        self.assertIsNone(format_metadata_date(None))

    def test_metadata_rows_format_dates_languages_and_countries(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 1,
                "imdb_id": None,
                "media_type": "movie",
                "title": "Example",
                "original_title": "Example",
                "production_status": "Released",
                "release_date": "2026-07-17",
                "runtime_min": 120,
                "genres": [],
                "spoken_languages": [
                    {"code": "en", "name": "English"},
                    {"code": "es", "name": "Spanish"},
                ],
                "origin_language": {"code": "es", "name": "Spanish"},
                "production_countries": [
                    {"code": "ES", "name": "Spain"},
                    {"code": "FI", "name": "Finland"},
                ],
                "production_companies": [],
                "directors": [],
                "writers": [],
                "actors": [],
            },
            "series_view": None,
        })
        row_texts = [row["text"] for row in rows]

        self.assertIn("Release Date: 17 Jul 2026, Fri", row_texts)
        self.assertIn("Spoken Languages: English, Spanish", row_texts)
        self.assertIn("Origin Language: Spanish", row_texts)
        self.assertIn("Production Countries: Spain, Finland", row_texts)

    def test_series_metadata_rows_format_first_and_last_air_dates(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 1,
                "imdb_id": None,
                "media_type": "series",
                "title": "Example",
                "original_title": "Example",
                "production_status": "Ended",
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "creators": [],
                "actors": [],
            },
            "series_view": {
                "summary": {
                    "first_air_date": "2024-01-01",
                    "last_air_date": "2026-07-17",
                },
            },
        })
        row_texts = [row["text"] for row in rows]

        self.assertIn("First Air Date: 1 Jan 2024, Mon", row_texts)
        self.assertIn("Last Air Date: 17 Jul 2026, Fri", row_texts)

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

        self.assertEqual(row_texts[0], "IMDb ID: None")
        self.assertIn("TMDB ID: <a", row_texts[1])
        self.assertEqual(row_texts[2], "Type: Movie")
        self.assertEqual(row_texts[-1], "Last Sync: None")
        self.assertIn("IMDb ID: None", row_texts)
        self.assertIn("Original Title: None", row_texts)
        self.assertIn("Runtime: None", row_texts)
        self.assertIn("Genres: None", row_texts)
        self.assertNotIn("Season Count: None", row_texts)

    def test_metadata_rows_show_last_sync_when_available(self):
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
                "last_tmdb_metadata_checked_at": "2026-06-29 11:53:44",
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

        self.assertIn("29 Jun 2026", row_texts[-1])
        self.assertRegex(row_texts[-1], r"Last Sync: .*\d{2}:\d{2}")

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

    def test_tmdb_row_has_external_link_marker_and_tooltip_for_movie(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 77,
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
        tmdb_row = next(row for row in rows if row["text"].startswith("TMDB ID:"))

        self.assertIn("https://www.themoviedb.org/movie/77", tmdb_row["text"])
        self.assertIn("77 ↗", tmdb_row["text"])
        self.assertEqual(tmdb_row["tooltip"], "Open on TMDB")

    def test_tmdb_row_has_external_link_for_series(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 83867,
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
                "writers": [],
                "actors": [],
            },
            "series_view": {"summary": {}},
        })
        tmdb_row = next(row for row in rows if row["text"].startswith("TMDB ID:"))

        self.assertIn("https://www.themoviedb.org/tv/83867", tmdb_row["text"])

    def test_tmdb_row_has_external_link_for_episode(self):
        rows = build_metadata_display_rows({
            "metadata": {
                "tmdb_id": 1226006,
                "imdb_id": None,
                "media_type": "episode",
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
                "episode_details": {
                    "series_tmdb_id": 42009,
                    "series_title": "Example Series",
                    "season_num": 3,
                    "episode_num": 1,
                },
            },
            "series_view": None,
        })
        tmdb_row = next(row for row in rows if row["text"].startswith("TMDB ID:"))

        self.assertIn(
            "https://www.themoviedb.org/tv/42009/season/3/episode/1",
            tmdb_row["text"],
        )

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
        self.assertIsNone(format_watch_provider_checked_at())
        self.assertIsNone(format_watch_provider_checked_at(""))

    def test_format_watch_provider_checked_at_formats_timestamp(self):
        formatted = format_watch_provider_checked_at("2026-06-29 11:53:44")

        self.assertIn("29 Jun 2026", formatted)
        self.assertRegex(formatted, r"\d{2}:\d{2}")

    def test_format_watch_provider_checked_at_ignores_invalid_value(self):
        self.assertIsNone(format_watch_provider_checked_at("not-a-date"))

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
            "Mar-Jun 2022",
        )
        self.assertEqual(
            format_watch_history_entry({
                "date_earliest": "2022-01-01",
                "date_latest": "2022-12-31",
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
            "~2000-2025",
        )

    def test_watch_history_entries_sort_by_estimated_watch_date_newest_first(self):
        media_draft = {
            "metadata": {
                "media_type": "movie",
                "release_date": "2020-01-01",
            },
            "user_data": {
                "watch_history": [
                    {
                        "id": 1,
                        "date_earliest": "2026-01-01",
                        "date_latest": "2026-01-01",
                        "created_at": "2026-01-02 10:00:00",
                    },
                    {
                        "id": 2,
                        "date_earliest": "2024-01-01",
                        "date_latest": "2026-01-01",
                        "created_at": "2026-02-01 10:00:00",
                    },
                    {
                        "id": 3,
                        "date_earliest": "2024-01-01",
                        "date_latest": None,
                        "created_at": "2026-01-01 10:00:00",
                    },
                    {
                        "id": 4,
                        "date_earliest": None,
                        "date_latest": "2030-01-01",
                        "created_at": "2028-01-01 10:00:00",
                    },
                    {
                        "id": 5,
                        "date_earliest": None,
                        "date_latest": None,
                        "created_at": "2027-01-01T10:00:00Z",
                    },
                ],
            },
        }

        entries = build_watch_history_display_entries(media_draft)

        self.assertEqual(
            [entry["watch_history_id"] for entry in entries],
            [5, 1, 2, 4, 3],
        )

    def test_watch_history_order_tiebreaks_by_created_time_then_id(self):
        media_draft = {
            "metadata": {
                "media_type": "movie",
                "release_date": "2020-01-01",
            },
            "user_data": {
                "watch_history": [
                    {
                        "id": 11,
                        "date_earliest": "2026-06-01",
                        "date_latest": "2026-06-01",
                        "created_at": "2026-06-02 10:00:00",
                    },
                    {
                        "id": 12,
                        "date_earliest": "2026-06-01",
                        "date_latest": "2026-06-01",
                        "created_at": "2026-06-02 10:00:00",
                    },
                    {
                        "id": 10,
                        "date_earliest": "2026-06-01",
                        "date_latest": "2026-06-01",
                        "created_at": "2026-06-02 12:00:00",
                    },
                ],
            },
        }

        entries = build_watch_history_display_entries(media_draft)

        self.assertEqual(
            [entry["watch_history_id"] for entry in entries],
            [10, 12, 11],
        )

    def test_watch_history_order_accepts_date_and_datetime_values(self):
        media_draft = {
            "metadata": {
                "media_type": "movie",
                "release_date": date(2020, 1, 1),
            },
            "user_data": {
                "watch_history": [
                    {
                        "id": 1,
                        "date_earliest": date(2026, 1, 1),
                        "date_latest": datetime(2026, 1, 1, 20, 0),
                        "created_at": datetime(2026, 1, 2, 10, 0),
                    },
                    {
                        "id": 2,
                        "date_earliest": date(2026, 2, 1),
                        "date_latest": date(2026, 2, 1),
                        "created_at": datetime(2026, 2, 2, 10, 0),
                    },
                ],
            },
        }

        entries = build_watch_history_display_entries(media_draft)

        self.assertEqual(
            [entry["watch_history_id"] for entry in entries],
            [2, 1],
        )

    def test_series_history_combines_entries_by_estimated_watch_date(self):
        media_draft = {
            "metadata": {
                "media_type": "series",
                "release_date": "2020-01-01",
            },
            "user_data": {
                "watch_history": [
                    {
                        "id": 50,
                        "date_earliest": "2026-06-10",
                        "date_latest": "2026-06-10",
                        "created_at": "2030-01-01 10:00:00",
                    },
                ],
            },
            "series_view": {
                "summary": {"first_air_date": "2020-01-01"},
                "episode_watch_history": [
                    {
                        "series_id": 10,
                        "episode_id": 101,
                        "watch_history_id": 40,
                        "date_earliest": "2026-06-20",
                        "date_latest": "2026-06-20",
                        "created_at": "2020-01-01 10:00:00",
                        "season_num": 1,
                        "episode_num": 1,
                    },
                    {
                        "series_id": 10,
                        "episode_id": 102,
                        "watch_history_id": 60,
                        "date_earliest": "2026-06-20",
                        "date_latest": "2026-06-20",
                        "created_at": "2020-01-01 10:01:00",
                        "season_num": 1,
                        "episode_num": 2,
                    },
                    {
                        "series_id": 10,
                        "episode_id": 103,
                        "watch_history_id": 70,
                        "date_earliest": None,
                        "date_latest": None,
                        "created_at": "2027-01-01 10:00:00",
                        "season_num": 1,
                        "episode_num": 3,
                    },
                ],
            },
        }

        entries = build_watch_history_display_entries(media_draft)

        self.assertEqual(
            [entry["kind"] for entry in entries],
            ["episode_group", "episode_group", "media_event"],
        )
        self.assertEqual(entries[0]["watch_history_ids"], [70])
        self.assertEqual(entries[1]["watch_history_ids"], [40, 60])
        self.assertEqual(entries[2]["watch_history_id"], 50)

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
                        "series_id": 10,
                        "episode_id": 104,
                        "watch_history_id": 1,
                        "date_earliest": "2026-05-01",
                        "date_latest": "2026-05-01",
                        "created_at": "2026-05-01 20:00:00",
                        "season_num": 1,
                        "episode_num": 4,
                    },
                    {
                        "series_id": 10,
                        "episode_id": 105,
                        "watch_history_id": 2,
                        "date_earliest": "2026-05-01",
                        "date_latest": "2026-05-01",
                        "created_at": "2026-05-01 20:01:00",
                        "season_num": 1,
                        "episode_num": 5,
                    },
                    {
                        "series_id": 10,
                        "episode_id": 106,
                        "watch_history_id": 3,
                        "date_earliest": "2026-05-01",
                        "date_latest": "2026-05-01",
                        "created_at": "2026-05-01 20:02:00",
                        "season_num": 1,
                        "episode_num": 6,
                    },
                ],
            },
        }

        self.assertEqual(
            build_series_watch_history_lines(media_draft),
            ["1 May 2026, Fri · S1:E4-6"],
        )

        entries = build_watch_history_display_entries(media_draft)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "episode_group")
        self.assertEqual(entries[0]["date_earliest"], "2026-05-01")
        self.assertEqual(entries[0]["date_latest"], "2026-05-01")
        self.assertEqual(entries[0]["watch_history_ids"], [1, 2, 3])
        self.assertEqual(
            entries[0]["episodes"],
            [
                {
                    "series_id": 10,
                    "episode_id": 104,
                    "tmdb_id": None,
                    "watch_history_id": 1,
                    "draft_id": None,
                    "season_num": 1,
                    "episode_num": 4,
                    "created_at": "2026-05-01 20:00:00",
                },
                {
                    "series_id": 10,
                    "episode_id": 105,
                    "tmdb_id": None,
                    "watch_history_id": 2,
                    "draft_id": None,
                    "season_num": 1,
                    "episode_num": 5,
                    "created_at": "2026-05-01 20:01:00",
                },
                {
                    "series_id": 10,
                    "episode_id": 106,
                    "tmdb_id": None,
                    "watch_history_id": 3,
                    "draft_id": None,
                    "season_num": 1,
                    "episode_num": 6,
                    "created_at": "2026-05-01 20:02:00",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
