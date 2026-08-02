import os
import unittest
from unittest.mock import patch


os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")

import app.tmdb_fetcher as tmdb_fetcher


class TmdbTitleSearchTests(unittest.TestCase):
    def test_fetches_at_most_five_pages_and_preserves_api_order(self):
        calls = []

        def fake_get(endpoint, params):
            calls.append((endpoint, dict(params)))
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
                    "id": page,
                    "name": f"Series {page}",
                    "original_name": f"Original Series {page}",
                    "first_air_date": f"201{page}-01-01",
                    "poster_path": f"/series-{page}.jpg",
                }],
            }

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get):
            candidates = tmdb_fetcher.search_tmdb_title_candidates(
                "  Star Wars: Episode I – Test!  ",
            )

        self.assertEqual(
            calls,
            [
                *[(
                    "search/movie",
                    {
                        "query": "Star Wars: Episode I – Test!",
                        "language": "en-US",
                        "page": page,
                    },
                ) for page in range(1, 6)],
                *[(
                    "search/tv",
                    {
                        "query": "Star Wars: Episode I – Test!",
                        "language": "en-US",
                        "page": page,
                    },
                ) for page in range(1, 6)],
            ],
        )
        self.assertEqual(
            [(item["media_type"], item["tmdb_id"]) for item in candidates],
            [
                ("movie", 1),
                ("movie", 2),
                ("movie", 3),
                ("movie", 4),
                ("movie", 5),
                ("series", 1),
                ("series", 2),
                ("series", 3),
                ("series", 4),
                ("series", 5),
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
        self.assertEqual(candidates[5]["title"], "Series 1")

    def test_zero_results_fetches_only_the_first_page_of_each_endpoint(self):
        calls = []

        def fake_get(endpoint, params):
            calls.append((endpoint, dict(params)))
            return {"total_pages": 0, "total_results": 0, "results": []}

        with patch.object(tmdb_fetcher, "_tmdb_get", side_effect=fake_get):
            candidates = tmdb_fetcher.search_tmdb_title_candidates("Unknown")

        self.assertEqual(candidates, [])
        self.assertEqual(
            [(endpoint, params["page"]) for endpoint, params in calls],
            [("search/movie", 1), ("search/tv", 1)],
        )

    def test_results_without_ids_are_ignored_without_reordering_valid_items(self):
        responses = {
            "search/movie": {
                "total_pages": 1,
                "results": [
                    {"title": "Missing ID"},
                    {"id": 20, "title": "First Valid"},
                    {"id": 10, "title": "Second Valid"},
                ],
            },
            "search/tv": {"total_pages": 1, "results": []},
        }

        with patch.object(
            tmdb_fetcher,
            "_tmdb_get",
            side_effect=lambda endpoint, params: responses[endpoint],
        ):
            candidates = tmdb_fetcher.search_tmdb_title_candidates("Title")

        self.assertEqual(
            [candidate["tmdb_id"] for candidate in candidates],
            [20, 10],
        )

    def test_empty_query_does_not_call_tmdb(self):
        with patch.object(tmdb_fetcher, "_tmdb_get") as get_mock:
            candidates = tmdb_fetcher.search_tmdb_title_candidates("   ")

        self.assertEqual(candidates, [])
        get_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
