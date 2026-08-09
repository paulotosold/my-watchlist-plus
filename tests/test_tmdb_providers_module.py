import unittest
from unittest.mock import Mock

from app.tmdb import providers


class TmdbProvidersTests(unittest.TestCase):
    def test_formats_configured_access_types_in_order_and_deduplicates(self):
        watch_provider_data = {
            "results": {
                "AT": {
                    "flatrate": [
                        {"provider_id": 8, "provider_name": "Netflix"},
                        {"provider_id": 8, "provider_name": "Netflix"},
                        {"provider_id": None, "provider_name": "Missing ID"},
                    ],
                    "rent": [
                        {"provider_id": 8, "provider_name": "Netflix"},
                        {"provider_id": 2, "provider_name": "Apple TV"},
                    ],
                    "buy": [
                        {"provider_id": 3, "provider_name": "Amazon"},
                        {"provider_id": 4, "provider_name": ""},
                    ],
                    "free": [
                        {"provider_id": 5, "provider_name": "Ignored"},
                    ],
                }
            }
        }

        result = providers._format_watch_providers(
            watch_provider_data,
            "AT",
        )

        self.assertEqual(
            result,
            [
                {
                    "provider_tmdb_id": 8,
                    "provider_name": "Netflix",
                    "country_code": "AT",
                    "access_type": "flatrate",
                },
                {
                    "provider_tmdb_id": 8,
                    "provider_name": "Netflix",
                    "country_code": "AT",
                    "access_type": "rent",
                },
                {
                    "provider_tmdb_id": 2,
                    "provider_name": "Apple TV",
                    "country_code": "AT",
                    "access_type": "rent",
                },
                {
                    "provider_tmdb_id": 3,
                    "provider_name": "Amazon",
                    "country_code": "AT",
                    "access_type": "buy",
                },
            ],
        )

    def test_missing_country_returns_an_empty_list(self):
        result = providers._format_watch_providers(
            {"results": {"US": {"flatrate": []}}},
            "AT",
        )

        self.assertEqual(result, [])

    def test_movie_series_and_episode_use_the_expected_endpoints(self):
        cases = (
            (
                {"media_type": "movie", "tmdb_id": 1},
                "movie/1/watch/providers",
            ),
            (
                {"media_type": "series", "tmdb_id": 2},
                "tv/2/watch/providers",
            ),
            (
                {
                    "media_type": "episode",
                    "tmdb_id": 3,
                    "series_tmdb_id": 20,
                    "season_num": 4,
                },
                "tv/20/season/4/watch/providers",
            ),
        )

        for match, expected_endpoint in cases:
            with self.subTest(media_type=match["media_type"]):
                client = Mock()
                client.get_json.return_value = {"results": {}}

                result = providers.get_tmdb_media_watch_providers(
                    match,
                    country_code="AT",
                    client=client,
                )

                self.assertEqual(result, [])
                client.get_json.assert_called_once_with(expected_endpoint)

    def test_movie_wrapper_preserves_country_and_formats_result(self):
        client = Mock()
        client.get_json.return_value = {
            "results": {
                "DE": {
                    "flatrate": [
                        {"provider_id": 8, "provider_name": "Netflix"},
                    ]
                }
            }
        }

        result = providers.get_tmdb_movie_watch_providers(
            7,
            country_code="DE",
            client=client,
        )

        client.get_json.assert_called_once_with("movie/7/watch/providers")
        self.assertEqual(result[0]["country_code"], "DE")

    def test_resolved_wrapper_is_accepted(self):
        client = Mock()
        client.get_json.return_value = {"results": {}}

        providers.get_tmdb_media_watch_providers(
            {
                "status": "resolved",
                "match": {"media_type": "series", "tmdb_id": 12},
            },
            client=client,
        )

        client.get_json.assert_called_once_with("tv/12/watch/providers")

    def test_invalid_matches_media_types_and_episode_context_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "requires a resolved"):
            providers.get_tmdb_media_watch_providers(
                {"status": "not_found", "match": None},
                client=Mock(),
            )

        with self.assertRaisesRegex(ValueError, "Episode watch providers"):
            providers.get_tmdb_media_watch_providers(
                {"media_type": "episode", "tmdb_id": 3},
                client=Mock(),
            )

        with self.assertRaisesRegex(ValueError, "Unsupported media_type"):
            providers.get_tmdb_media_watch_providers(
                {"media_type": "person", "tmdb_id": 4},
                client=Mock(),
            )


if __name__ == "__main__":
    unittest.main()
