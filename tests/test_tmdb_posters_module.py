import unittest
from unittest.mock import Mock, call

from app.config import TMDB_LANGUAGE
from app.tmdb import posters


def poster_payload(file_path, *, language="en"):
    return {
        "file_path": file_path,
        "iso_639_1": language,
        "aspect_ratio": 0.667,
        "width": 1000,
        "height": 1500,
    }


class TmdbPostersTests(unittest.TestCase):
    def test_formats_only_eligible_unique_posters(self):
        image_data = {
            "posters": [
                poster_payload("/english.jpg"),
                poster_payload("/original.jpg", language="pt"),
                poster_payload("/neutral.jpg", language=None),
                poster_payload("/other-language.jpg", language="de"),
                poster_payload("/english.jpg"),
                {
                    **poster_payload("/too-narrow.jpg"),
                    "aspect_ratio": 0.63,
                },
                {**poster_payload("/too-small.jpg"), "width": 499},
                {**poster_payload("/too-short.jpg"), "height": 749},
                {**poster_payload(None)},
            ]
        }

        result = posters._format_tmdb_posters(
            image_data,
            scope="season",
            original_language="pt",
            series_tmdb_id=42,
            season_num=3,
        )

        self.assertEqual(
            [poster["filename"] for poster in result],
            ["english.jpg", "original.jpg", "neutral.jpg"],
        )
        self.assertTrue(all(
            poster == {
                "scope": "season",
                "filename": poster["filename"],
                "source": "tmdb",
                "curation_status": "pending",
                "is_default": False,
                "series_tmdb_id": 42,
                "season_num": 3,
            }
            for poster in result
        ))

    def test_movie_posters_use_original_language_in_image_request(self):
        client = Mock()
        client.get_json.side_effect = [
            {"original_language": "pt"},
            {"posters": [poster_payload("/movie.jpg", language="pt")]},
        ]

        result = posters.get_tmdb_movie_posters(7, client=client)

        self.assertEqual(result[0]["filename"], "movie.jpg")
        self.assertEqual(result[0]["scope"], "media")
        self.assertEqual(
            client.get_json.call_args_list,
            [
                call("movie/7"),
                call(
                    "movie/7/images",
                    params={
                        "language": TMDB_LANGUAGE,
                        "include_image_language": "en,null,pt",
                    },
                ),
            ],
        )

    def test_episode_posters_include_season_before_series(self):
        client = Mock()
        client.get_json.side_effect = [
            {"original_language": "en"},
            {"posters": [poster_payload("/season.jpg")]},
            {"posters": [poster_payload("/series.jpg")]},
        ]

        result = posters.get_tmdb_media_posters(
            {
                "media_type": "episode",
                "tmdb_id": 99,
                "series_tmdb_id": 42,
                "season_num": 2,
            },
            client=client,
        )

        self.assertEqual(
            [(item["scope"], item["filename"]) for item in result],
            [("season", "season.jpg"), ("series", "series.jpg")],
        )
        self.assertEqual(result[0]["series_tmdb_id"], 42)
        self.assertEqual(result[0]["season_num"], 2)
        self.assertIsNone(result[1]["season_num"])

    def test_primary_season_posters_are_unique_sorted_and_skip_specials(self):
        client = Mock()
        client.get_json.return_value = {
            "seasons": [
                {"season_number": 2, "poster_path": "/two.jpg"},
                {"season_number": 0, "poster_path": "/specials.jpg"},
                {"season_number": 1, "poster_path": "/one.jpg"},
                {"season_number": 2, "poster_path": "/duplicate.jpg"},
                {"season_number": 3, "poster_path": None},
            ]
        }

        result = posters.get_tmdb_series_primary_season_posters(
            42,
            client=client,
        )

        client.get_json.assert_called_once_with("tv/42")
        self.assertEqual(
            [(item["season_num"], item["filename"]) for item in result],
            [(1, "one.jpg"), (2, "two.jpg")],
        )

    def test_resolved_wrapper_is_accepted(self):
        client = Mock()
        client.get_json.side_effect = [
            {"original_language": "en"},
            {"posters": []},
        ]

        result = posters.get_tmdb_media_posters(
            {
                "status": "resolved",
                "match": {"media_type": "series", "tmdb_id": 12},
            },
            client=client,
        )

        self.assertEqual(result, [])
        self.assertEqual(client.get_json.call_args_list[0], call("tv/12"))

    def test_invalid_matches_and_episode_context_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "requires a resolved"):
            posters.get_tmdb_media_posters(
                {"status": "ambiguous", "match": None},
                client=Mock(),
            )

        with self.assertRaisesRegex(ValueError, "Episode posters require"):
            posters.get_tmdb_media_posters(
                {"media_type": "episode", "tmdb_id": 99},
                client=Mock(),
            )

        with self.assertRaisesRegex(ValueError, "Unsupported media_type"):
            posters.get_tmdb_media_posters(
                {"media_type": "person", "tmdb_id": 1},
                client=Mock(),
            )

    def test_build_tmdb_image_url_normalizes_valid_paths(self):
        self.assertEqual(
            posters.build_tmdb_image_url(" /poster image.jpg ", "w92"),
            "https://image.tmdb.org/t/p/w92/poster%20image.jpg",
        )
        self.assertEqual(
            posters.build_tmdb_image_url("poster.jpg", "original"),
            "https://image.tmdb.org/t/p/original/poster.jpg",
        )

    def test_build_tmdb_image_url_rejects_unsafe_values(self):
        for file_path, size in (
            (None, "w500"),
            ("", "w500"),
            ("https://example.com/poster.jpg", "w500"),
            ("../poster.jpg", "w500"),
            ("folder/poster.jpg", "w500"),
            ("poster.jpg?token=secret", "w500"),
            ("poster.jpg", "full"),
            ("poster.jpg", "w500/../../bad"),
        ):
            with self.subTest(file_path=file_path, size=size):
                self.assertIsNone(
                    posters.build_tmdb_image_url(file_path, size)
                )


if __name__ == "__main__":
    unittest.main()
