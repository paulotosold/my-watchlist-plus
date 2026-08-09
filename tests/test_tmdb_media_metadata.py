import unittest
from unittest.mock import Mock, call

from app.tmdb import metadata as tmdb_metadata
from app.tmdb.search import find_tmdb_match_by_imdb_id


class TmdbMediaMetadataTests(unittest.TestCase):
    def test_movie_metadata_fetches_details_and_credits_into_canonical_shape(self):
        responses = {
            "movie/7": {
                "id": 7,
                "imdb_id": "tt0000007",
                "title": "Localized Movie",
                "original_title": "Original Movie",
                "status": "Released",
                "release_date": "2024-04-05",
                "runtime": 123,
                "genres": [{"id": 18, "name": "Drama"}],
                "spoken_languages": [
                    {
                        "iso_639_1": "fr",
                        "english_name": "French",
                        "name": "Français",
                    }
                ],
                "original_language": "fr",
                "production_countries": [
                    {"iso_3166_1": "FR", "name": "France"}
                ],
                "production_companies": [{"id": 70, "name": "Studio"}],
            },
            "movie/7/credits": {
                "crew": [
                    {"id": 71, "name": "Director", "job": "Director"},
                    {"id": 72, "name": "Writer", "job": "Screenplay"},
                ],
                "cast": [
                    {
                        "id": 73,
                        "name": "Actor",
                        "character": "Lead",
                        "order": 0,
                    }
                ],
            },
        }

        client = Mock()
        client.get_json.side_effect = lambda endpoint: responses[endpoint]
        metadata = tmdb_metadata.get_tmdb_media_metadata(
            {"media_type": "movie", "tmdb_id": 7},
            client=client,
        )

        self.assertEqual(
            metadata,
            {
                "tmdb_id": 7,
                "imdb_id": "tt0000007",
                "media_type": "movie",
                "title": "Localized Movie",
                "original_title": "Original Movie",
                "production_status": "Released",
                "release_date": "2024-04-05",
                "runtime_min": 123,
                "genres": [
                    {"tmdb_id": 18, "name": "Drama", "tmdb_scope": "movie_series"}
                ],
                "spoken_languages": [{"code": "fr", "name": "French"}],
                "origin_language": {"code": "fr", "name": "French"},
                "production_countries": [{"code": "FR", "name": "France"}],
                "production_companies": [{"tmdb_id": 70, "name": "Studio"}],
                "directors": [{"tmdb_id": 71, "name": "Director"}],
                "creators": [],
                "writers": [
                    {"tmdb_id": 72, "name": "Writer", "job": "Screenplay"}
                ],
                "actors": [
                    {
                        "tmdb_id": 73,
                        "name": "Actor",
                        "character": "Lead",
                        "cast_order": 0,
                    }
                ],
                "episode_details": None,
            },
        )
        self.assertEqual(
            client.get_json.call_args_list,
            [call("movie/7"), call("movie/7/credits")],
        )

    def test_series_metadata_fetches_external_ids_and_series_credits(self):
        responses = {
            "tv/42": {
                "id": 42,
                "name": "Localized Series",
                "original_name": "Original Series",
                "status": "Returning Series",
                "first_air_date": "2020-01-02",
                "genres": [{"id": 10765, "name": "Sci-Fi & Fantasy"}],
                "spoken_languages": [
                    {"iso_639_1": "en", "english_name": "English"}
                ],
                "original_language": "en",
                "production_countries": [
                    {"iso_3166_1": "US", "name": "United States"}
                ],
                "production_companies": [{"id": 420, "name": "Network"}],
                "created_by": [{"id": 421, "name": "Creator"}],
            },
            "tv/42/external_ids": {"imdb_id": "tt0000042"},
            "tv/42/credits": {
                "crew": [
                    {"id": 422, "name": "Director", "job": "Director"},
                    {"id": 423, "name": "Writer", "job": "Writer"},
                ],
                "cast": [
                    {
                        "id": 424,
                        "name": "Series Actor",
                        "character": "Hero",
                        "order": 1,
                    }
                ],
            },
        }

        client = Mock()
        client.get_json.side_effect = lambda endpoint: responses[endpoint]
        metadata = tmdb_metadata.get_tmdb_media_metadata(
            {"media_type": "series", "tmdb_id": 42},
            client=client,
        )

        self.assertEqual(metadata["tmdb_id"], 42)
        self.assertEqual(metadata["imdb_id"], "tt0000042")
        self.assertEqual(metadata["media_type"], "series")
        self.assertEqual(metadata["title"], "Localized Series")
        self.assertEqual(metadata["original_title"], "Original Series")
        self.assertEqual(metadata["runtime_min"], None)
        self.assertEqual(
            metadata["genres"],
            [
                {
                    "tmdb_id": 10765,
                    "name": "Sci-Fi & Fantasy",
                    "tmdb_scope": "series",
                }
            ],
        )
        self.assertEqual(metadata["creators"], [{"tmdb_id": 421, "name": "Creator"}])
        self.assertEqual(metadata["directors"], [{"tmdb_id": 422, "name": "Director"}])
        self.assertEqual(
            metadata["writers"],
            [{"tmdb_id": 423, "name": "Writer", "job": "Writer"}],
        )
        self.assertIsNone(metadata["episode_details"])
        self.assertEqual(
            client.get_json.call_args_list,
            [
                call("tv/42"),
                call("tv/42/external_ids"),
                call("tv/42/credits"),
            ],
        )

    def test_episode_metadata_uses_parent_context_and_episode_specific_credits(self):
        episode_endpoint = "tv/42/season/2/episode/3"
        responses = {
            "tv/42": {
                "id": 42,
                "name": "Parent Series",
                "status": "Ended",
                "genres": [{"id": 18, "name": "Drama"}],
                "spoken_languages": [
                    {"iso_639_1": "en", "english_name": "English"}
                ],
                "original_language": "en",
                "production_countries": [
                    {"iso_3166_1": "GB", "name": "United Kingdom"}
                ],
                "production_companies": [{"id": 425, "name": "Producer"}],
                "created_by": [{"id": 426, "name": "Creator"}],
            },
            "tv/42/external_ids": {"imdb_id": "tt0000042"},
            episode_endpoint: {
                "id": 203,
                "name": "Episode Three",
                "air_date": "2021-03-04",
                "runtime": 48,
            },
            f"{episode_endpoint}/external_ids": {"imdb_id": "tt0000203"},
            f"{episode_endpoint}/credits": {
                "crew": [
                    {"id": 427, "name": "Episode Director", "job": "Director"},
                    {"id": 428, "name": "Episode Writer", "job": "Teleplay"},
                ],
                "cast": [
                    {
                        "id": 429,
                        "name": "Regular",
                        "character": "Regular Role",
                        "order": 0,
                    }
                ],
                "guest_stars": [
                    {
                        "id": 430,
                        "name": "Guest",
                        "character": "Guest Role",
                        "order": 2,
                    }
                ],
            },
        }

        client = Mock()
        client.get_json.side_effect = lambda endpoint: responses[endpoint]
        metadata = tmdb_metadata.get_tmdb_media_metadata(
            {
                "status": "resolved",
                "match": {
                    "media_type": "episode",
                    "tmdb_id": 203,
                    "series_tmdb_id": 42,
                    "season_num": 2,
                    "episode_num": 3,
                },
            },
            client=client,
        )

        self.assertEqual(metadata["tmdb_id"], 203)
        self.assertEqual(metadata["imdb_id"], "tt0000203")
        self.assertEqual(metadata["media_type"], "episode")
        self.assertEqual(metadata["title"], "Episode Three")
        self.assertEqual(metadata["original_title"], "Episode Three")
        self.assertEqual(metadata["production_status"], "Ended")
        self.assertEqual(metadata["runtime_min"], 48)
        self.assertEqual(
            metadata["episode_details"],
            {
                "series_tmdb_id": 42,
                "series_imdb_id": "tt0000042",
                "series_title": "Parent Series",
                "season_num": 2,
                "episode_num": 3,
            },
        )
        self.assertEqual(
            metadata["directors"],
            [{"tmdb_id": 427, "name": "Episode Director"}],
        )
        self.assertEqual(
            metadata["writers"],
            [{"tmdb_id": 428, "name": "Episode Writer", "job": "Teleplay"}],
        )
        self.assertEqual(
            [actor["name"] for actor in metadata["actors"]],
            ["Regular", "Guest"],
        )
        self.assertEqual(
            client.get_json.call_args_list,
            [
                call("tv/42"),
                call("tv/42/external_ids"),
                call(episode_endpoint),
                call(f"{episode_endpoint}/external_ids"),
                call(f"{episode_endpoint}/credits"),
            ],
        )

    def test_series_view_reuses_details_and_excludes_local_watch_history(self):
        client = Mock()
        client.get_json.side_effect = [
            {
                "number_of_seasons": 1,
                "number_of_episodes": 1,
                "first_air_date": "2024-01-01",
                "last_air_date": "2024-01-08",
                "seasons": [{"season_number": 1, "episode_count": 1}],
            },
            {
                "episodes": [{
                    "id": 101,
                    "season_number": 1,
                    "episode_number": 1,
                    "name": "Pilot",
                    "air_date": "2024-01-01",
                }],
            },
        ]

        series_view = tmdb_metadata.get_tmdb_media_series_view(
            {"media_type": "series", "tmdb_id": 42},
            client=client,
        )

        self.assertEqual(set(series_view), {"summary", "episodes"})
        self.assertEqual(series_view["episodes"][0]["tmdb_id"], 101)
        self.assertEqual(
            client.get_json.call_args_list,
            [call("tv/42"), call("tv/42/season/1")],
        )

    def test_imdb_find_returns_one_resolved_movie_match(self):
        client = Mock()
        client.get_json.return_value = {
            "movie_results": [
                {
                    "id": 7,
                    "title": "Movie",
                    "release_date": "2024-04-05",
                }
            ],
            "tv_results": [],
            "tv_episode_results": [],
        }

        result = find_tmdb_match_by_imdb_id(
            " tt0000007 ",
            client=client,
        )

        self.assertEqual(
            result,
            {
                "status": "resolved",
                "match": {
                    "media_type": "movie",
                    "tmdb_id": 7,
                    "title": "Movie",
                    "release_date": "2024-04-05",
                },
            },
        )
        client.get_json.assert_called_once_with(
            "find/tt0000007",
            params={
                "external_source": "imdb_id",
                "language": "en-US",
            },
        )

    def test_imdb_find_preserves_category_order_for_ambiguous_matches(self):
        client = Mock()
        client.get_json.return_value = {
            "movie_results": [
                {
                    "id": 1,
                    "title": "Movie",
                    "release_date": "2001-01-01",
                }
            ],
            "tv_results": [
                {
                    "id": 2,
                    "name": "Series",
                    "first_air_date": "2002-02-02",
                }
            ],
            "tv_episode_results": [
                {
                    "id": 3,
                    "name": "Episode",
                    "air_date": "2003-03-03",
                    "show_id": 2,
                    "season_number": 4,
                    "episode_number": 5,
                }
            ],
        }

        result = find_tmdb_match_by_imdb_id(
            "tt0000001",
            client=client,
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["match"])
        self.assertEqual(
            result["candidates"],
            [
                {
                    "media_type": "movie",
                    "tmdb_id": 1,
                    "title": "Movie",
                    "release_date": "2001-01-01",
                },
                {
                    "media_type": "series",
                    "tmdb_id": 2,
                    "title": "Series",
                    "release_date": "2002-02-02",
                },
                {
                    "media_type": "episode",
                    "tmdb_id": 3,
                    "title": "Episode",
                    "release_date": "2003-03-03",
                    "series_tmdb_id": 2,
                    "season_num": 4,
                    "episode_num": 5,
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
