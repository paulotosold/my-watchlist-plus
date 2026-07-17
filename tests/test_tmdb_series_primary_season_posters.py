import os
import unittest
from unittest.mock import patch


os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")

import app.tmdb_fetcher as tmdb_fetcher


class TmdbSeriesPrimarySeasonPostersTests(unittest.TestCase):
    def test_collects_regular_and_announced_seasons_with_one_request(self):
        series_details = {
            "seasons": [
                {
                    "season_number": 2,
                    "episode_count": 0,
                    "poster_path": "/season-two.jpg",
                },
                {
                    "season_number": 1,
                    "episode_count": 8,
                    "poster_path": "/season-one.jpg",
                },
            ],
        }

        with patch.object(
            tmdb_fetcher,
            "_tmdb_get",
            return_value=series_details,
        ) as get_mock:
            result = tmdb_fetcher.get_tmdb_series_primary_season_posters(42)

        get_mock.assert_called_once_with("tv/42")
        self.assertEqual(
            result,
            [
                {
                    "scope": "season",
                    "filename": "season-one.jpg",
                    "source": "tmdb",
                    "curation_status": "pending",
                    "is_default": False,
                    "series_tmdb_id": 42,
                    "season_num": 1,
                },
                {
                    "scope": "season",
                    "filename": "season-two.jpg",
                    "source": "tmdb",
                    "curation_status": "pending",
                    "is_default": False,
                    "series_tmdb_id": 42,
                    "season_num": 2,
                },
            ],
        )

    def test_skips_specials_missing_posters_and_duplicate_seasons(self):
        series_details = {
            "seasons": [
                {"season_number": 0, "poster_path": "/specials.jpg"},
                {"season_number": -1, "poster_path": "/negative.jpg"},
                {"season_number": None, "poster_path": "/unknown.jpg"},
                {"season_number": 1, "poster_path": None},
                {"season_number": 2},
                {"season_number": 3, "poster_path": "/first.jpg"},
                {"season_number": 3, "poster_path": "/duplicate.jpg"},
            ],
        }

        with patch.object(
            tmdb_fetcher,
            "_tmdb_get",
            return_value=series_details,
        ):
            result = tmdb_fetcher.get_tmdb_series_primary_season_posters(42)

        self.assertEqual(
            result,
            [
                {
                    "scope": "season",
                    "filename": "first.jpg",
                    "source": "tmdb",
                    "curation_status": "pending",
                    "is_default": False,
                    "series_tmdb_id": 42,
                    "season_num": 3,
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
