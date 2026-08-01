import os
import sqlite3
import unittest
from unittest.mock import patch


os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")

import app.media_title_lookup as media_title_lookup


class MediaTitleNormalizationTests(unittest.TestCase):
    def test_ignores_case_whitespace_colons_and_dash_family(self):
        variants = [
            " Star Wars:  Starfighter ",
            "STAR WARS - STARFIGHTER",
            "Star Wars ‐ Starfighter",
            "Star Wars ‑ Starfighter",
            "Star Wars ‒ Starfighter",
            "Star Wars – Starfighter",
            "Star Wars — Starfighter",
            "Star Wars ― Starfighter",
        ]

        self.assertEqual(
            {media_title_lookup.normalize_title(value) for value in variants},
            {"star wars starfighter"},
        )

    def test_preserves_accents_apostrophes_and_other_punctuation(self):
        self.assertEqual(
            media_title_lookup.normalize_title("L’Amour, Máquina!"),
            "l’amour, máquina!",
        )
        self.assertNotEqual(
            media_title_lookup.normalize_title("Maquina"),
            media_title_lookup.normalize_title("Máquina"),
        )


class MediaTitleLookupTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE media (
                id INTEGER PRIMARY KEY,
                tmdb_id INTEGER NOT NULL,
                imdb_id TEXT,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                original_title TEXT,
                production_status TEXT,
                release_date TEXT,
                runtime_min INTEGER,
                last_tmdb_metadata_checked_at TEXT,
                last_tmdb_posters_checked_at TEXT,
                last_tmdb_watch_providers_checked_at TEXT,
                UNIQUE (tmdb_id, media_type)
            );

            CREATE TABLE media_posters (
                id INTEGER PRIMARY KEY,
                media_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                curation_status TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0
            );
            """
        )

    def tearDown(self):
        self.conn.close()

    def test_local_search_is_exact_and_excludes_episodes(self):
        self._insert_media(1, 10, "movie", "Robin Hood", "Robin Hood")
        self._insert_media(
            2,
            11,
            "movie",
            "The Death of Robin Hood",
            "The Death of Robin Hood",
        )
        self._insert_media(3, 12, "series", "Robín: Hood", "Other")
        self._insert_media(4, 13, "episode", "Robin Hood", "Robin Hood")

        matches = media_title_lookup.find_local_title_matches(
            self.conn,
            "robin — hood",
        )

        self.assertEqual([match["media_id"] for match in matches], [1])

    def test_local_search_matches_original_title_and_prefers_local_poster(self):
        self._insert_media(
            1,
            941,
            "movie",
            "Máquina Mortífera",
            "Lethal Weapon",
            imdb_id="tt0093409",
            release_date="1987-03-06",
        )
        self.conn.executemany(
            """
            INSERT INTO media_posters (
                id, media_id, filename, curation_status, is_default
            ) VALUES (?, 1, ?, ?, ?)
            """,
            [
                (1, "pending.jpg", "pending", 0),
                (2, "selected.jpg", "selected", 0),
                (3, "default.jpg", "selected", 1),
                (4, "discarded.jpg", "discarded", 0),
            ],
        )

        matches = media_title_lookup.find_local_title_matches(
            self.conn,
            "lethal weapon",
        )

        self.assertEqual(
            matches,
            [{
                "source": "db",
                "media_id": 1,
                "media_type": "movie",
                "tmdb_id": 941,
                "imdb_id": "tt0093409",
                "title": "Máquina Mortífera",
                "original_title": "Lethal Weapon",
                "localized_titles": [],
                "alternate_titles": [],
                "release_date": "1987-03-06",
                "poster_path": "default.jpg",
            }],
        )

    def test_tmdb_search_keeps_only_exact_supported_matches(self):
        candidates = [
            self._tmdb_candidate(941, "movie", "Lethal Weapon"),
            self._tmdb_candidate(942, "movie", "Lethal Weapon 2"),
            self._tmdb_candidate(
                943,
                "series",
                "Arma Letal",
                localized_titles=["Máquina Mortífera"],
            ),
            self._tmdb_candidate(944, "episode", "Máquina Mortífera"),
        ]

        with patch.object(
            media_title_lookup.tmdb_fetcher,
            "search_tmdb_title_candidates",
            return_value=candidates,
        ) as search_mock:
            matches = media_title_lookup.find_tmdb_title_matches(
                "  MÁQUINA: MORTÍFERA  "
            )

        search_mock.assert_called_once_with("MÁQUINA: MORTÍFERA")
        self.assertEqual(
            [(match["media_type"], match["tmdb_id"]) for match in matches],
            [("series", 943)],
        )

    def test_tmdb_filter_matches_default_original_and_localized_titles(self):
        candidates = [
            {
                **self._tmdb_candidate(1, "movie", "Exact Query"),
                "original_title": "Different Original",
            },
            {
                **self._tmdb_candidate(2, "movie", "Translated Title"),
                "original_title": "Exact Query",
            },
            self._tmdb_candidate(
                3,
                "series",
                "Localized Series",
                localized_titles=["Exact Query"],
            ),
            self._tmdb_candidate(4, "movie", "The Exact Query Story"),
        ]

        matches = media_title_lookup.filter_exact_tmdb_title_matches(
            candidates,
            "exact query",
        )

        self.assertEqual([match["tmdb_id"] for match in matches], [1, 2, 3])

    def test_tmdb_filter_matches_alternate_title(self):
        candidates = [
            self._tmdb_candidate(
                1891,
                "movie",
                "The Empire Strikes Back",
                alternate_titles=[
                    "Star Wars: Episode V - The Empire Strikes Back",
                    "Star Wars: The Empire Strikes Back",
                ],
            ),
            self._tmdb_candidate(
                1892,
                "movie",
                "The Empire Strikes Back: Revisited",
            ),
        ]

        matches = media_title_lookup.filter_exact_tmdb_title_matches(
            candidates,
            "star wars the empire strikes back",
        )

        self.assertEqual([match["tmdb_id"] for match in matches], [1891])

    def test_merge_prefers_db_preserves_tmdb_order_and_keeps_type_identity(self):
        self._insert_media(1, 7, "series", "Shared ID Series", "Robin Hood")
        self._insert_media(2, 50, "movie", "DB-only", "Robin Hood")
        local_matches = media_title_lookup.find_local_title_matches(
            self.conn,
            "robin hood",
        )
        tmdb_matches = [
            self._tmdb_candidate(8, "movie", "Robin Hood"),
            self._tmdb_candidate(7, "series", "Robin Hood"),
            self._tmdb_candidate(7, "movie", "Robin Hood"),
            self._tmdb_candidate(8, "movie", "Robin Hood"),
        ]

        merged = media_title_lookup.merge_title_matches(
            self.conn,
            local_matches,
            tmdb_matches,
        )

        self.assertEqual(
            [(match["media_type"], match["tmdb_id"]) for match in merged],
            [
                ("movie", 8),
                ("series", 7),
                ("movie", 7),
                ("movie", 50),
            ],
        )
        self.assertEqual(merged[1]["source"], "db")
        self.assertEqual(merged[1]["title"], "Shared ID Series")
        self.assertEqual(merged[-1]["source"], "db")

    def test_merge_converts_localized_remote_match_already_in_db(self):
        self._insert_media(
            4,
            941,
            "movie",
            "Lethal Weapon",
            "Lethal Weapon",
            imdb_id="tt0093409",
        )
        remote = self._tmdb_candidate(
            941,
            "movie",
            "Lethal Weapon",
            localized_titles=["Máquina Mortífera"],
        )

        local_matches = media_title_lookup.find_local_title_matches(
            self.conn,
            "máquina mortífera",
        )
        merged = media_title_lookup.merge_title_matches(
            self.conn,
            local_matches,
            [remote],
        )

        self.assertEqual(local_matches, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "db")
        self.assertEqual(merged[0]["media_id"], 4)
        self.assertEqual(merged[0]["title"], "Lethal Weapon")
        self.assertEqual(merged[0]["remote_poster_path"], "/poster.jpg")

    def test_top_level_calls_each_stage(self):
        with patch.object(
            media_title_lookup,
            "find_local_title_matches",
            return_value=[{"source": "db"}],
        ) as local_mock, patch.object(
            media_title_lookup,
            "find_tmdb_title_matches",
            return_value=[{"source": "tmdb"}],
        ) as tmdb_mock, patch.object(
            media_title_lookup,
            "merge_title_matches",
            return_value=[{"source": "merged"}],
        ) as merge_mock:
            result = media_title_lookup.find_exact_title_matches(
                self.conn,
                "Robin Hood",
            )

        self.assertEqual(result, [{"source": "merged"}])
        local_mock.assert_called_once_with(self.conn, "Robin Hood")
        tmdb_mock.assert_called_once_with("Robin Hood")
        merge_mock.assert_called_once_with(
            self.conn,
            [{"source": "db"}],
            [{"source": "tmdb"}],
        )

    def _insert_media(
        self,
        media_id,
        tmdb_id,
        media_type,
        title,
        original_title,
        *,
        imdb_id=None,
        release_date=None,
    ):
        self.conn.execute(
            """
            INSERT INTO media (
                id, tmdb_id, imdb_id, media_type, title, original_title,
                release_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                media_id,
                tmdb_id,
                imdb_id,
                media_type,
                title,
                original_title,
                release_date,
            ),
        )

    @staticmethod
    def _tmdb_candidate(
        tmdb_id,
        media_type,
        title,
        *,
        localized_titles=None,
        alternate_titles=None,
    ):
        return {
            "source": "tmdb",
            "media_id": None,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "imdb_id": None,
            "title": title,
            "original_title": title,
            "localized_titles": localized_titles or [],
            "alternate_titles": alternate_titles or [],
            "release_date": "2020-01-01",
            "poster_path": "/poster.jpg",
        }


if __name__ == "__main__":
    unittest.main()
