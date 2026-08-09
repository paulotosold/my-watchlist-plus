import unittest
from unittest.mock import Mock

from app.tmdb.posters import get_tmdb_series_primary_season_posters


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

        client = Mock()
        client.get_json.return_value = series_details
        result = get_tmdb_series_primary_season_posters(42, client=client)

        client.get_json.assert_called_once_with("tv/42")
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

        client = Mock()
        client.get_json.return_value = series_details
        result = get_tmdb_series_primary_season_posters(42, client=client)

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
