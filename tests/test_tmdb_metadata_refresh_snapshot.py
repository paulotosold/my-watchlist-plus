import os
import unittest
from concurrent.futures import CancelledError
from unittest.mock import Mock, patch

import requests

os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")

import app.tmdb_fetcher as tmdb_fetcher


CHECKED_AT = "2026-07-13 12:34:56"


class TmdbMetadataRefreshSnapshotTests(unittest.TestCase):
    def test_movie_snapshot_marks_all_root_metadata_as_loaded(self):
        responses = {
            "movie/7": {
                "id": 7,
                "imdb_id": "tt0000007",
                "title": "Movie",
                "original_title": "Original Movie",
                "status": "Released",
                "release_date": "2024-01-01",
                "runtime": 90,
                "original_language": "en",
                "spoken_languages": [],
                "genres": [],
                "production_countries": [],
                "production_companies": [],
            },
            "movie/7/credits": {
                "crew": [{"id": 8, "name": "Director", "job": "Director"}],
                "cast": [{"id": 9, "name": "Actor", "character": "Lead"}],
            },
        }
        get_mock = Mock(side_effect=lambda endpoint: responses[endpoint])

        with patch.object(tmdb_fetcher, "_tmdb_get", get_mock), patch.object(
            tmdb_fetcher,
            "current_sqlite_timestamp",
            return_value=CHECKED_AT,
        ):
            result = tmdb_fetcher.get_tmdb_metadata_refresh_snapshot({
                "status": "resolved",
                "match": {"media_type": "movie", "tmdb_id": 7},
            })

        self.assertEqual(
            [call.args[0] for call in get_mock.call_args_list],
            ["movie/7", "movie/7/credits"],
        )
        self.assertIsNone(result["regular_episodes"])
        self.assertIsNone(result["series_summary"])
        self.assertEqual(result["metadata"]["directors"][0]["tmdb_id"], 8)
        self.assertNotIn("last_tmdb_posters_checked_at", result["metadata"])
        self.assertNotIn(
            "last_tmdb_watch_providers_checked_at",
            result["metadata"],
        )
        self.assertEqual(
            set(result["loaded_fields"]["metadata"]),
            set(result["metadata"]),
        )

    def test_series_uses_one_call_per_regular_season(self):
        responses = {
            "tv/42": self._series_details(),
            "tv/42/external_ids": {"imdb_id": "tt0000042"},
            "tv/42/credits": {
                "crew": [{"id": 8, "name": "Director", "job": "Director"}],
                "cast": [{"id": 9, "name": "Actor", "character": "Lead"}],
            },
            "tv/42/season/1": {
                "episodes": [self._episode(101, 1, 1, "Pilot")],
            },
            "tv/42/season/2": {
                "episodes": [self._episode(201, 2, 1, "Return")],
            },
        }
        calls = []

        def fake_get(endpoint):
            calls.append(endpoint)
            return responses[endpoint]

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get), patch.object(
            tmdb_fetcher,
            "current_sqlite_timestamp",
            return_value=CHECKED_AT,
        ) as timestamp:
            result = tmdb_fetcher.get_tmdb_metadata_refresh_snapshot({
                "media_type": "series",
                "tmdb_id": 42,
            })

        self.assertEqual(
            calls,
            [
                "tv/42",
                "tv/42/external_ids",
                "tv/42/credits",
                "tv/42/season/1",
                "tv/42/season/2",
            ],
        )
        timestamp.assert_called_once_with()
        self.assertEqual(result["checked_at"], CHECKED_AT)
        self.assertEqual(result["metadata"]["last_tmdb_metadata_checked_at"], CHECKED_AT)
        self.assertEqual(
            [item["tmdb_id"] for item in result["regular_episodes"]],
            [101, 201],
        )
        self.assertTrue(all(
            item["last_tmdb_metadata_checked_at"] == CHECKED_AT
            for item in result["regular_episodes"]
        ))
        self.assertEqual(
            result["series_summary"]["episode_count"],
            3,
        )
        episode_fields = result["loaded_fields"]["regular_episodes"]
        self.assertIn("release_date", episode_fields)
        self.assertNotIn("imdb_id", episode_fields)
        self.assertNotIn("directors", episode_fields)
        self.assertNotIn("writers", episode_fields)
        self.assertNotIn("actors", episode_fields)

    def test_episode_identity_mismatch_is_relocated_and_refetched(self):
        responses = {
            "tv/42": self._series_details(),
            "tv/42/external_ids": {"imdb_id": "tt0000042"},
            "tv/42/season/1/episode/1": self._episode(999, 1, 1, "Replacement"),
            "tv/42/season/1": {
                "episodes": [self._episode(999, 1, 1, "Replacement")],
            },
            "tv/42/season/2": {
                "episodes": [self._episode(101, 2, 1, "Moved")],
            },
            "tv/42/season/2/episode/1": self._episode(101, 2, 1, "Moved"),
            "tv/42/season/2/episode/1/external_ids": {"imdb_id": "tt0101"},
            "tv/42/season/2/episode/1/credits": {
                "crew": [{"id": 7, "name": "Writer", "job": "Writer"}],
                "cast": [],
                "guest_stars": [],
            },
        }
        calls = []

        def fake_get(endpoint):
            calls.append(endpoint)
            return responses[endpoint]

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get), patch.object(
            tmdb_fetcher,
            "current_sqlite_timestamp",
            return_value=CHECKED_AT,
        ):
            result = tmdb_fetcher.get_tmdb_metadata_refresh_snapshot({
                "media_type": "episode",
                "tmdb_id": 101,
                "series_tmdb_id": 42,
                "season_num": 1,
                "episode_num": 1,
            })

        self.assertEqual(result["metadata"]["tmdb_id"], 101)
        self.assertEqual(
            result["metadata"]["episode_details"]["season_num"],
            2,
        )
        self.assertEqual(
            result["metadata"]["episode_details"]["episode_num"],
            1,
        )
        self.assertIn("tv/42/season/2/episode/1", calls)
        self.assertNotIn("tv/42/season/0", calls)
        self.assertEqual(calls[-2:], [
            "tv/42/season/2/episode/1/external_ids",
            "tv/42/season/2/episode/1/credits",
        ])

    def test_episode_404_is_relocated(self):
        not_found_response = Mock(status_code=404)
        not_found = requests.HTTPError(response=not_found_response)
        responses = {
            "tv/42": self._series_details(),
            "tv/42/external_ids": {"imdb_id": "tt0000042"},
            "tv/42/season/1/episode/1": not_found,
            "tv/42/season/1": {
                "episodes": [self._episode(101, 1, 2, "Moved")],
            },
            "tv/42/season/1/episode/2": self._episode(101, 1, 2, "Moved"),
            "tv/42/season/1/episode/2/external_ids": {"imdb_id": "tt0101"},
            "tv/42/season/1/episode/2/credits": {
                "crew": [],
                "cast": [],
                "guest_stars": [],
            },
        }

        def fake_get(endpoint):
            response = responses[endpoint]
            if isinstance(response, Exception):
                raise response
            return response

        series_details = responses["tv/42"]
        series_details["seasons"] = [
            {"season_number": 0, "episode_count": 1},
            {"season_number": 1, "episode_count": 2},
        ]

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get), patch.object(
            tmdb_fetcher,
            "current_sqlite_timestamp",
            return_value=CHECKED_AT,
        ):
            result = tmdb_fetcher.get_tmdb_metadata_refresh_snapshot({
                "media_type": "episode",
                "tmdb_id": 101,
                "series_tmdb_id": 42,
                "season_num": 1,
                "episode_num": 1,
            })

        self.assertEqual(
            result["metadata"]["episode_details"]["episode_num"],
            2,
        )

    def test_episode_relocation_fails_when_identity_is_absent(self):
        responses = {
            "tv/42": self._series_details(),
            "tv/42/external_ids": {"imdb_id": "tt0000042"},
            "tv/42/season/1/episode/1": self._episode(999, 1, 1, "Replacement"),
            "tv/42/season/1": {
                "episodes": [self._episode(999, 1, 1, "Replacement")],
            },
            "tv/42/season/2": {
                "episodes": [self._episode(201, 2, 1, "Other")],
            },
        }

        with patch.object(
            tmdb_fetcher,
            "_tmdb_get",
            side_effect=lambda endpoint: responses[endpoint],
        ), patch.object(
            tmdb_fetcher,
            "current_sqlite_timestamp",
            return_value=CHECKED_AT,
        ):
            with self.assertRaisesRegex(ValueError, "was not found"):
                tmdb_fetcher.get_tmdb_metadata_refresh_snapshot({
                    "media_type": "episode",
                    "tmdb_id": 101,
                    "series_tmdb_id": 42,
                    "season_num": 1,
                    "episode_num": 1,
                })

    def test_cancellation_between_calls_raises_cancelled_error(self):
        calls = []

        def fake_get(endpoint):
            calls.append(endpoint)
            return self._series_details()

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get):
            with self.assertRaises(CancelledError):
                tmdb_fetcher.get_tmdb_metadata_refresh_snapshot(
                    {"media_type": "series", "tmdb_id": 42},
                    should_cancel=lambda: bool(calls),
                )

        self.assertEqual(calls, ["tv/42"])

    def test_root_identity_mismatch_fails_before_followup_calls(self):
        get_mock = Mock(return_value={"id": 99})

        with patch.object(tmdb_fetcher, "_tmdb_get", get_mock):
            with self.assertRaisesRegex(ValueError, "different movie identity"):
                tmdb_fetcher.get_tmdb_metadata_refresh_snapshot({
                    "media_type": "movie",
                    "tmdb_id": 42,
                })

        get_mock.assert_called_once_with("movie/42")

    def _series_details(self):
        return {
            "id": 42,
            "name": "Series",
            "original_name": "Series Original",
            "status": "Returning Series",
            "first_air_date": "2024-01-01",
            "last_air_date": "2025-01-01",
            "number_of_seasons": 2,
            "number_of_episodes": 3,
            "original_language": "en",
            "spoken_languages": [
                {"iso_639_1": "en", "english_name": "English"},
            ],
            "genres": [{"id": 18, "name": "Drama"}],
            "production_countries": [
                {"iso_3166_1": "US", "name": "United States"},
            ],
            "production_companies": [{"id": 3, "name": "Studio"}],
            "created_by": [{"id": 4, "name": "Creator"}],
            "seasons": [
                {"season_number": 0, "episode_count": 1},
                {"season_number": 1, "episode_count": 2},
                {"season_number": 2, "episode_count": 1},
            ],
        }

    def _episode(self, tmdb_id, season_num, episode_num, title):
        return {
            "id": tmdb_id,
            "season_number": season_num,
            "episode_number": episode_num,
            "name": title,
            "air_date": "2025-01-01",
            "runtime": 50,
        }


if __name__ == "__main__":
    unittest.main()
