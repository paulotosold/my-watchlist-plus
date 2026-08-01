import os
import unittest
from unittest.mock import Mock, patch


os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")

from app import config
import app.tmdb_fetcher as tmdb_fetcher


class TmdbTitleSearchTests(unittest.TestCase):
    def test_config_normalizes_additional_languages_without_reordering(self):
        self.assertEqual(
            config._normalize_additional_languages(
                [" pt-BR ", "", "en-us", "PT-br", None, "de-DE"],
                "en-US",
            ),
            ["pt-BR", "de-DE"],
        )
        self.assertEqual(
            config.DEFAULT_SETTINGS["tmdb"]["additional_languages"],
            [],
        )

    def test_searches_two_pages_and_enriches_only_base_identities(self):
        responses = {
            ("search/movie", "en-US", 1): {
                "total_results": 41,
                "total_pages": 3,
                "results": [
                    {
                        "id": 941,
                        "title": "Lethal Weapon",
                        "original_title": "Lethal Weapon",
                        "release_date": "1987-03-06",
                        "poster_path": "/lethal.jpg",
                    },
                    {
                        "id": 942,
                        "title": "Lethal Weapon 2",
                        "original_title": "Lethal Weapon 2",
                        "release_date": "1989-07-07",
                        "poster_path": "/lethal-2.jpg",
                    },
                ],
            },
            ("search/movie", "en-US", 2): {
                "results": [{
                    "id": 943,
                    "title": "Another Movie",
                    "original_title": "Another Movie",
                    "release_date": "1990-01-01",
                    "poster_path": None,
                }],
            },
            ("search/tv", "en-US", 1): {
                "total_results": 1,
                "total_pages": 1,
                "results": [{
                    "id": 941,
                    "name": "Lethal Series",
                    "original_name": "Lethal Series",
                    "first_air_date": "2020-05-01",
                    "poster_path": "/series.jpg",
                }],
            },
            ("search/movie", "pt-BR", 1): {
                "total_results": 3,
                "total_pages": 2,
                "results": [
                    {"id": 941, "title": "Máquina Mortífera"},
                    {"id": 942, "title": "Máquina Mortífera 2"},
                    {"id": 9999, "title": "Portuguese-only result"},
                ],
            },
            ("search/movie", "pt-BR", 2): {
                "results": [{"id": 943, "title": "Outro Filme"}],
            },
            ("search/tv", "pt-BR", 1): {
                "total_results": 1,
                "total_pages": 1,
                "results": [{"id": 941, "name": "Série Letal"}],
            },
            ("search/movie", "de-DE", 1): {
                "total_results": 1,
                "total_pages": 1,
                "results": [{
                    "id": 941,
                    "title": "Zwei stahlharte Profis - Lethal Weapon",
                }],
            },
            ("search/tv", "de-DE", 1): {
                "total_results": 1,
                "total_pages": 1,
                "results": [{"id": 941, "name": "Tödliche Serie"}],
            },
        }
        alternative_responses = {
            "movie/941/alternative_titles": {
                "titles": [
                    {"iso_3166_1": "US", "title": "Lethal Weapon"},
                    {
                        "iso_3166_1": "US",
                        "title": "  Lethal Weapon: The Movie  ",
                        "type": "working title",
                    },
                    {"iso_3166_1": "BR", "title": "Máquina Mortífera"},
                    {"iso_3166_1": "DE", "title": "Zwei Profis"},
                    {"iso_3166_1": "FR", "title": "L'Arme fatale"},
                ],
            },
            "movie/942/alternative_titles": {"titles": []},
            "movie/943/alternative_titles": {"titles": []},
            "tv/941/alternative_titles": {
                "results": [
                    {"iso_3166_1": "US", "title": "Lethal TV"},
                    {"iso_3166_1": "FR", "title": "Série mortelle"},
                ],
            },
        }
        calls = []

        def fake_get(endpoint, params):
            calls.append((endpoint, dict(params)))

            if endpoint.startswith("search/"):
                return responses[(endpoint, params["language"], params["page"])]

            return alternative_responses[endpoint]

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get):
            candidates = tmdb_fetcher.search_tmdb_title_candidates(
                "  máquina mortífera  ",
                additional_languages=[
                    " pt-BR ",
                    "",
                    "en-us",
                    "PT-br",
                    None,
                    "de-DE",
                ],
            )

        self.assertEqual(
            [
                (call[0], call[1]["language"], call[1]["page"])
                for call in calls[:8]
            ],
            [
                ("search/movie", "en-US", 1),
                ("search/movie", "en-US", 2),
                ("search/tv", "en-US", 1),
                ("search/movie", "pt-BR", 1),
                ("search/movie", "pt-BR", 2),
                ("search/tv", "pt-BR", 1),
                ("search/movie", "de-DE", 1),
                ("search/tv", "de-DE", 1),
            ],
        )
        self.assertEqual(
            [(endpoint, params) for endpoint, params in calls[8:]],
            [
                ("movie/941/alternative_titles", {}),
                ("movie/942/alternative_titles", {}),
                ("movie/943/alternative_titles", {}),
                ("tv/941/alternative_titles", {}),
            ],
        )
        self.assertTrue(all(
            call[1]["query"] == "máquina mortífera"
            and set(call[1]) == {"query", "language", "page"}
            for call in calls[:8]
        ))
        self.assertEqual(
            [(candidate["media_type"], candidate["tmdb_id"])
             for candidate in candidates],
            [
                ("movie", 941),
                ("movie", 942),
                ("movie", 943),
                ("series", 941),
            ],
        )
        self.assertEqual(
            candidates[0],
            {
                "source": "tmdb",
                "media_id": None,
                "media_type": "movie",
                "tmdb_id": 941,
                "imdb_id": None,
                "title": "Lethal Weapon",
                "original_title": "Lethal Weapon",
                "localized_titles": [
                    "Máquina Mortífera",
                    "Zwei stahlharte Profis - Lethal Weapon",
                ],
                "alternate_titles": [
                    "Lethal Weapon: The Movie",
                    "Zwei Profis",
                ],
                "release_date": "1987-03-06",
                "poster_path": "/lethal.jpg",
            },
        )
        self.assertEqual(candidates[1]["localized_titles"], ["Máquina Mortífera 2"])
        self.assertEqual(candidates[1]["alternate_titles"], [])
        self.assertEqual(candidates[2]["localized_titles"], ["Outro Filme"])
        self.assertEqual(candidates[2]["alternate_titles"], [])
        self.assertEqual(
            candidates[3]["localized_titles"],
            ["Série Letal", "Tödliche Serie"],
        )
        self.assertEqual(candidates[3]["alternate_titles"], ["Lethal TV"])
        self.assertNotIn(
            9999,
            [candidate["tmdb_id"] for candidate in candidates],
        )

    def test_alternate_titles_are_limited_to_top_three_per_media_type(self):
        movies = [
            {
                "id": media_id,
                "title": f"Movie {media_id}",
                "original_title": f"Movie {media_id}",
            }
            for media_id in range(1, 5)
        ]
        series = [
            {
                "id": media_id,
                "name": f"Series {media_id}",
                "original_name": f"Series {media_id}",
            }
            for media_id in range(1, 5)
        ]
        calls = []

        def fake_get(endpoint, params):
            calls.append((endpoint, dict(params)))

            if endpoint == "search/movie":
                return {
                    "total_results": 4,
                    "total_pages": 1,
                    "results": movies,
                }

            if endpoint == "search/tv":
                return {
                    "total_results": 4,
                    "total_pages": 1,
                    "results": series,
                }

            media_type, media_id, _ = endpoint.split("/")
            collection_key = "titles" if media_type == "movie" else "results"
            return {
                collection_key: [{
                    "iso_3166_1": "US",
                    "title": f"Alias {media_type} {media_id}",
                }],
            }

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get):
            candidates = tmdb_fetcher.search_tmdb_title_candidates(
                "anything",
                additional_languages=[],
            )

        alternate_calls = [
            call for call in calls
            if call[0].endswith("/alternative_titles")
        ]
        self.assertEqual(
            alternate_calls,
            [
                ("movie/1/alternative_titles", {}),
                ("movie/2/alternative_titles", {}),
                ("movie/3/alternative_titles", {}),
                ("tv/1/alternative_titles", {}),
                ("tv/2/alternative_titles", {}),
                ("tv/3/alternative_titles", {}),
            ],
        )
        self.assertEqual(len(alternate_calls), 6)
        self.assertEqual(candidates[0]["alternate_titles"], ["Alias movie 1"])
        self.assertEqual(candidates[3]["alternate_titles"], [])
        self.assertEqual(candidates[4]["alternate_titles"], ["Alias tv 1"])
        self.assertEqual(candidates[7]["alternate_titles"], [])

    def test_alternate_titles_filter_countries_and_dedupe_literal_values(self):
        candidate = {
            "title": "Canonical",
            "original_title": "Original",
            "localized_titles": ["Localized"],
            "alternate_titles": [],
            "tmdb_id": 99,
        }
        response = {
            "titles": [
                {"iso_3166_1": "US", "title": " Canonical "},
                {"iso_3166_1": "BR", "title": "Localized"},
                {"iso_3166_1": "de", "title": " Alias "},
                {"iso_3166_1": "DE", "title": "Alias"},
                {"iso_3166_1": "US", "title": "alias"},
                {"iso_3166_1": "US", "title": "  "},
                {"iso_3166_1": "US", "title": None},
                {"iso_3166_1": "FR", "title": "French Alias"},
                {"iso_3166_1": None, "title": "Unknown Country"},
            ],
        }

        with patch.object(tmdb_fetcher, "_tmdb_get", return_value=response) as get_mock:
            tmdb_fetcher._enrich_tmdb_alternate_titles(
                [candidate],
                "movie",
                ["US", "BR", "DE"],
            )

        get_mock.assert_called_once_with(
            "movie/99/alternative_titles",
            params={},
        )
        self.assertEqual(candidate["alternate_titles"], ["Alias", "alias"])

    def test_country_codes_come_from_locale_region_subtags(self):
        self.assertEqual(
            tmdb_fetcher._tmdb_title_country_codes([
                " en-US ",
                "pt-BR",
                "de-DE",
                "EN-us",
                "en",
                "zh-Hant-TW",
                "es-419",
                "fr-éé",
                None,
            ]),
            ["US", "BR", "DE", "TW"],
        )

    def test_alternate_title_failure_propagates_without_partial_result(self):
        def fake_get(endpoint, params):
            if endpoint == "search/movie":
                return {
                    "total_results": 1,
                    "total_pages": 1,
                    "results": [{
                        "id": 1,
                        "title": "Movie",
                        "original_title": "Movie",
                    }],
                }

            if endpoint == "search/tv":
                return {
                    "total_results": 0,
                    "total_pages": 0,
                    "results": [],
                }

            raise RuntimeError("alternative titles unavailable")

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get):
            with self.assertRaisesRegex(
                RuntimeError,
                "alternative titles unavailable",
            ):
                tmdb_fetcher.search_tmdb_title_candidates(
                    "Movie",
                    additional_languages=[],
                )

    def test_tmdb_get_distinguishes_default_params_from_empty_params(self):
        response = Mock()
        response.json.return_value = {"ok": True}

        with patch.object(tmdb_fetcher.requests, "get", return_value=response) as get_mock:
            tmdb_fetcher._tmdb_get("movie/1")
            default_call = get_mock.call_args
            tmdb_fetcher._tmdb_get("movie/1/alternative_titles", params={})
            empty_call = get_mock.call_args

        self.assertEqual(default_call.kwargs["params"], {"language": "en-US"})
        self.assertEqual(empty_call.kwargs["params"], {})
        self.assertEqual(response.raise_for_status.call_count, 2)

    def test_zero_default_results_skips_all_additional_languages(self):
        calls = []

        def fake_get(endpoint, params):
            calls.append((endpoint, dict(params)))
            return {
                "total_results": 0,
                "total_pages": 0,
                "results": [],
            }

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get):
            candidates = tmdb_fetcher.search_tmdb_title_candidates(
                "Unknown",
                additional_languages=["pt-BR", "de-DE"],
            )

        self.assertEqual(candidates, [])
        self.assertEqual(
            [(call[0], call[1]["language"], call[1]["page"]) for call in calls],
            [
                ("search/movie", "en-US", 1),
                ("search/tv", "en-US", 1),
            ],
        )

    def test_empty_query_does_not_call_tmdb(self):
        with patch.object(tmdb_fetcher, "_tmdb_get") as get_mock:
            candidates = tmdb_fetcher.search_tmdb_title_candidates("   ")

        self.assertEqual(candidates, [])
        get_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
