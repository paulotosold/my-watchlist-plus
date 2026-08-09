import unittest
from unittest.mock import Mock

from app.tmdb.search import (
    find_tmdb_match_by_imdb_id,
    search_tmdb_title_candidates,
)


class TmdbSearchTests(unittest.TestCase):
    def test_title_search_uses_injected_client_and_caps_each_result_at_five_pages(self):
        client = Mock()

        def fake_get(endpoint, params):
            page = params["page"]

            if endpoint == "search/movie":
                return {
                    "total_pages": 8,
                    "results": [{
                        "id": page,
                        "title": f"Movie {page}",
                        "original_title": f"Original Movie {page}",
                        "release_date": f"200{page}-01-01",
                        "poster_path": f"/movie-{page}.jpg",
                    }],
                }

            return {
                "total_pages": 8,
                "results": [{
                    "id": 100 + page,
                    "name": f"Series {page}",
                    "original_name": f"Original Series {page}",
                    "first_air_date": f"201{page}-01-01",
                    "poster_path": f"/series-{page}.jpg",
                }],
            }

        client.get_json.side_effect = fake_get
        candidates = search_tmdb_title_candidates(
            "  Star Wars: Episode I – Test!  ",
            client=client,
        )

        self.assertEqual(
            [
                (request.args[0], request.kwargs["params"]["page"])
                for request in client.get_json.call_args_list
            ],
            [
                *[("search/movie", page) for page in range(1, 6)],
                *[("search/tv", page) for page in range(1, 6)],
            ],
        )
        self.assertEqual(
            [(item["media_type"], item["tmdb_id"]) for item in candidates],
            [
                *[("movie", page) for page in range(1, 6)],
                *[("series", 100 + page) for page in range(1, 6)],
            ],
        )
        self.assertEqual(
            candidates[0],
            {
                "source": "tmdb",
                "media_id": None,
                "media_type": "movie",
                "tmdb_id": 1,
                "imdb_id": None,
                "title": "Movie 1",
                "original_title": "Original Movie 1",
                "release_date": "2001-01-01",
                "poster_path": "/movie-1.jpg",
            },
        )

    def test_empty_title_query_never_resolves_or_calls_client(self):
        client = Mock()

        self.assertEqual(
            search_tmdb_title_candidates("   ", client=client),
            [],
        )
        client.get_json.assert_not_called()

    def test_injected_client_language_is_used_by_default(self):
        client = Mock()
        client.language = "pt-BR"
        client.get_json.return_value = {
            "total_pages": 1,
            "results": [],
        }

        search_tmdb_title_candidates("Cidade", client=client)

        self.assertEqual(
            [
                request.kwargs["params"]["language"]
                for request in client.get_json.call_args_list
            ],
            ["pt-BR", "pt-BR"],
        )

    def test_imdb_find_preserves_resolved_episode_shape(self):
        client = Mock()
        client.get_json.return_value = {
            "movie_results": [],
            "tv_results": [],
            "tv_episode_results": [{
                "id": 12,
                "name": "Episode title",
                "air_date": "2026-08-01",
                "show_id": 34,
                "season_number": 2,
                "episode_number": 5,
            }],
        }

        result = find_tmdb_match_by_imdb_id(
            "  tt1234567  ",
            client=client,
        )

        client.get_json.assert_called_once_with(
            "find/tt1234567",
            params={
                "external_source": "imdb_id",
                "language": "en-US",
            },
        )
        self.assertEqual(
            result,
            {
                "status": "resolved",
                "match": {
                    "media_type": "episode",
                    "tmdb_id": 12,
                    "title": "Episode title",
                    "release_date": "2026-08-01",
                    "series_tmdb_id": 34,
                    "season_num": 2,
                    "episode_num": 5,
                },
            },
        )

    def test_imdb_find_preserves_ambiguous_candidate_order(self):
        client = Mock()
        client.get_json.return_value = {
            "movie_results": [{"id": 1, "title": "Movie"}],
            "tv_results": [{"id": 2, "name": "Series"}],
            "tv_episode_results": [{"id": 3, "name": "Episode"}],
        }

        result = find_tmdb_match_by_imdb_id("tt1234567", client=client)

        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["match"])
        self.assertEqual(
            [candidate["media_type"] for candidate in result["candidates"]],
            ["movie", "series", "episode"],
        )

    def test_imdb_find_preserves_not_found_result(self):
        client = Mock()
        client.get_json.return_value = {}

        result = find_tmdb_match_by_imdb_id("tt1234567", client=client)

        self.assertEqual(
            result,
            {
                "status": "not_found",
                "match": None,
                "reason": (
                    "IMDb ID did not match any TMDB movie, series, or episode."
                ),
            },
        )


if __name__ == "__main__":
    unittest.main()
