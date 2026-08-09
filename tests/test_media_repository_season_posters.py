import sqlite3
import unittest
from unittest.mock import patch

from app import media_repository
from app.media_repository import catalog as media_catalog_repository
from db.connection import apply_database_schema


class MediaRepositorySeasonPosterTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_insert_missing_deduplicates_by_season_and_is_idempotent(self):
        series_id = self._insert_media(100, "series", "Series")

        inserted = media_repository.insert_missing_series_season_posters(
            self.conn,
            series_id,
            [
                self._poster(1, "season-one.jpg"),
                self._poster(1, "duplicate-season-one.jpg"),
                self._poster(2, "season-two.jpg"),
            ],
        )

        self.assertEqual(inserted, 2)
        self.assertEqual(
            self._season_poster_rows(series_id),
            [
                (1, "season-one.jpg", "tmdb", "pending", 0),
                (2, "season-two.jpg", "tmdb", "pending", 0),
            ],
        )

        inserted = media_repository.insert_missing_series_season_posters(
            self.conn,
            series_id,
            [
                self._poster(1, "replacement-one.jpg"),
                self._poster(2, "replacement-two.jpg"),
            ],
        )

        self.assertEqual(inserted, 0)
        self.assertEqual(
            self._season_poster_rows(series_id),
            [
                (1, "season-one.jpg", "tmdb", "pending", 0),
                (2, "season-two.jpg", "tmdb", "pending", 0),
            ],
        )

    def test_insert_missing_preserves_any_existing_row_for_season(self):
        series_id = self._insert_media(200, "series", "Series")
        self._insert_season_poster(
            series_id,
            1,
            "curated.jpg",
            curation_status="selected",
            is_default=True,
        )

        inserted = media_repository.insert_missing_series_season_posters(
            self.conn,
            series_id,
            [
                self._poster(1, "tmdb-new.jpg"),
                self._poster(2, "season-two.jpg"),
            ],
        )

        self.assertEqual(inserted, 1)
        self.assertEqual(
            self._season_poster_rows(series_id),
            [
                (1, "curated.jpg", "tmdb", "selected", 1),
                (2, "season-two.jpg", "tmdb", "pending", 0),
            ],
        )

    def test_insert_missing_requires_a_series_owner(self):
        movie_id = self._insert_media(300, "movie", "Movie")

        for series_id in (movie_id, 999, True, 0):
            with self.subTest(series_id=series_id):
                with self.assertRaises(ValueError):
                    media_repository.insert_missing_series_season_posters(
                        self.conn,
                        series_id,
                        [self._poster(1, "poster.jpg")],
                    )

        with self.assertRaises(ValueError):
            media_repository.insert_missing_series_season_posters(
                self.conn,
                movie_id,
                [],
            )

        self.assertEqual(self._season_poster_count(), 0)

    def test_insert_missing_validates_all_rows_before_writing(self):
        series_id = self._insert_media(400, "series", "Series")
        invalid_posters = (
            None,
            {"scope": "media", "season_num": 1, "filename": "poster.jpg"},
            {"scope": "season", "season_num": 0, "filename": "poster.jpg"},
            {"scope": "season", "season_num": -1, "filename": "poster.jpg"},
            {"scope": "season", "season_num": True, "filename": "poster.jpg"},
            {"scope": "season", "season_num": 1.0, "filename": "poster.jpg"},
            {"scope": "season", "season_num": "1", "filename": "poster.jpg"},
            {"scope": "season", "season_num": 1, "filename": ""},
            {"scope": "season", "season_num": 1, "filename": "   "},
            {"scope": "season", "season_num": 1, "filename": " poster.jpg"},
            {"scope": "season", "season_num": 1, "filename": "poster.jpg "},
            {"scope": "season", "season_num": 1, "filename": "."},
            {"scope": "season", "season_num": 1, "filename": ".."},
            {"scope": "season", "season_num": 1, "filename": "/poster.jpg"},
            {"scope": "season", "season_num": 1, "filename": "dir/poster.jpg"},
            {"scope": "season", "season_num": 1, "filename": "dir\\poster.jpg"},
            {"scope": "season", "season_num": 1, "filename": "bad\x00name.jpg"},
            {
                **self._poster(1, "poster.jpg"),
                "source": "invalid",
            },
            {
                **self._poster(1, "poster.jpg"),
                "curation_status": "invalid",
            },
            {
                **self._poster(1, "poster.jpg"),
                "is_default": 1,
            },
            {
                **self._poster(1, "poster.jpg"),
                "is_default": True,
            },
        )

        for invalid_poster in invalid_posters:
            with self.subTest(invalid_poster=invalid_poster):
                with self.assertRaises(ValueError):
                    media_repository.insert_missing_series_season_posters(
                        self.conn,
                        series_id,
                        [self._poster(2, "valid.jpg"), invalid_poster],
                    )
                self.assertEqual(self._season_poster_count(), 0)

    def test_empty_input_does_not_query_or_mutate_season_posters(self):
        series_id = self._insert_media(500, "series", "Series")
        self._insert_season_poster(series_id, 1, "existing.jpg")
        statements = []
        self.conn.set_trace_callback(statements.append)

        inserted = media_repository.insert_missing_series_season_posters(
            self.conn,
            series_id,
            [],
        )

        self.conn.set_trace_callback(None)
        self.assertEqual(inserted, 0)
        self.assertFalse(any("SEASON_POSTERS" in sql.upper() for sql in statements))
        self.assertEqual(
            self._season_poster_rows(series_id),
            [(1, "existing.jpg", "tmdb", "pending", 0)],
        )

    def test_episode_empty_seed_preserves_existing_season_poster(self):
        series_id = self._insert_media(700, "series", "Series")
        self._insert_season_poster(series_id, 1, "existing.jpg")
        statements = []
        self.conn.set_trace_callback(statements.append)

        media_repository.save_media_catalog_draft(
            self.conn,
            self._episode_draft(701, 700, posters=[]),
        )

        self.conn.set_trace_callback(None)
        self.assertFalse(any(
            "DELETE FROM SEASON_POSTERS" in sql.upper()
            for sql in statements
        ))
        self.assertEqual(
            self._season_poster_rows(series_id),
            [(1, "existing.jpg", "tmdb", "pending", 0)],
        )

    def test_empty_automatic_poster_list_preserves_existing_media_poster(self):
        series_id = self._insert_media(750, "series", "Series")
        self.conn.execute(
            """
            INSERT INTO media_posters (
                media_id, filename, source, curation_status, is_default
            )
            VALUES (?, 'curated.jpg', 'user', 'selected', 1)
            """,
            (series_id,),
        )

        media_repository.save_media_catalog_draft(
            self.conn,
            {
                "metadata": {
                    "tmdb_id": 750,
                    "media_type": "series",
                    "title": "Series",
                },
                "watch_providers": [],
                "posters": [],
            },
        )

        row = self.conn.execute(
            """
            SELECT filename, source, curation_status, is_default
            FROM media_posters
            WHERE media_id = ?
            """,
            (series_id,),
        ).fetchone()
        self.assertEqual(
            tuple(row),
            ("curated.jpg", "user", "selected", 1),
        )

    def test_automatic_tmdb_poster_never_replaces_curated_media_poster(self):
        series_id = self._insert_media(760, "series", "Series")
        self.conn.execute(
            """
            INSERT INTO media_posters (
                media_id, filename, source, curation_status, is_default
            )
            VALUES (?, 'curated.jpg', 'user', 'selected', 1)
            """,
            (series_id,),
        )

        media_repository.save_media_catalog_draft(
            self.conn,
            {
                "metadata": {
                    "tmdb_id": 760,
                    "media_type": "series",
                    "title": "Series",
                },
                "watch_providers": [],
                "posters": [{
                    "scope": "media",
                    "filename": "new-tmdb.jpg",
                    "source": "tmdb",
                    "curation_status": "pending",
                    "is_default": False,
                }],
            },
        )

        rows = self.conn.execute(
            """
            SELECT filename, source, curation_status, is_default
            FROM media_posters
            WHERE media_id = ?
            """,
            (series_id,),
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in rows],
            [("curated.jpg", "user", "selected", 1)],
        )

    def test_episode_posters_never_replace_parent_rows(self):
        series_id = self._insert_media(
            800,
            "series",
            "Series",
            posters_checked_at="parent-old",
        )
        self._insert_season_poster(series_id, 1, "existing-season.jpg")
        self.conn.execute(
            """
            INSERT INTO media_posters (
                media_id, filename, source, curation_status, is_default
            )
            VALUES (?, 'existing-series.jpg', 'user', 'selected', 1)
            """,
            (series_id,),
        )
        posters = [
            self._poster(1, "inherited-season.jpg"),
            {
                "scope": "series",
                "filename": "inherited-series.jpg",
                "source": "tmdb",
                "curation_status": "pending",
                "is_default": False,
            },
        ]

        with patch.object(
            media_catalog_repository,
            "TMDB_MAX_POSTERS_PER_MEDIA",
            None,
        ):
            episode_id = media_repository.save_media_catalog_draft(
                self.conn,
                self._episode_draft(
                    801,
                    800,
                    posters=posters,
                    posters_checked_at="episode-new",
                ),
            )

        self.assertEqual(
            self._season_poster_rows(series_id),
            [(1, "existing-season.jpg", "tmdb", "pending", 0)],
        )
        parent_posters = self.conn.execute(
            """
            SELECT filename, source, curation_status, is_default
            FROM media_posters
            WHERE media_id = ?
            """,
            (series_id,),
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in parent_posters],
            [("existing-series.jpg", "user", "selected", 1)],
        )

        self.assertEqual(self._posters_checked_at(series_id), "parent-old")
        self.assertIsNone(self._posters_checked_at(episode_id))

    def test_episode_save_preserves_legacy_poster_timestamp(self):
        series_id = self._insert_media(900, "series", "Series")
        episode_id = self._insert_media(
            901,
            "episode",
            "Episode",
            posters_checked_at="episode-old",
        )
        self.conn.execute(
            """
            INSERT INTO episode_details (
                media_id, series_id, season_num, episode_num
            )
            VALUES (?, ?, 1, 1)
            """,
            (episode_id, series_id),
        )

        saved_episode_id = media_repository.save_media_catalog_draft(
            self.conn,
            self._episode_draft(
                901,
                900,
                posters=[],
                posters_checked_at="episode-new",
            ),
        )

        self.assertEqual(saved_episode_id, episode_id)
        self.assertEqual(self._posters_checked_at(episode_id), "episode-old")

    def _insert_media(
        self,
        tmdb_id,
        media_type,
        title,
        posters_checked_at=None,
    ):
        return self.conn.execute(
            """
            INSERT INTO media (
                tmdb_id,
                media_type,
                title,
                last_tmdb_posters_checked_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (tmdb_id, media_type, title, posters_checked_at),
        ).lastrowid

    def _insert_season_poster(
        self,
        series_id,
        season_num,
        filename,
        curation_status="pending",
        is_default=False,
    ):
        self.conn.execute(
            """
            INSERT INTO season_posters (
                series_id,
                season_num,
                filename,
                source,
                curation_status,
                is_default
            )
            VALUES (?, ?, ?, 'tmdb', ?, ?)
            """,
            (
                series_id,
                season_num,
                filename,
                curation_status,
                int(is_default),
            ),
        )

    def _season_poster_rows(self, series_id):
        rows = self.conn.execute(
            """
            SELECT season_num, filename, source, curation_status, is_default
            FROM season_posters
            WHERE series_id = ?
            ORDER BY season_num, filename
            """,
            (series_id,),
        ).fetchall()
        return [tuple(row) for row in rows]

    def _season_poster_count(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM season_posters"
        ).fetchone()[0]

    def _posters_checked_at(self, media_id):
        return self.conn.execute(
            """
            SELECT last_tmdb_posters_checked_at
            FROM media
            WHERE id = ?
            """,
            (media_id,),
        ).fetchone()[0]

    def _poster(self, season_num, filename):
        return {
            "scope": "season",
            "season_num": season_num,
            "filename": filename,
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False,
        }

    def _episode_draft(
        self,
        tmdb_id,
        series_tmdb_id,
        posters,
        posters_checked_at=None,
    ):
        return {
            "metadata": {
                "tmdb_id": tmdb_id,
                "media_type": "episode",
                "title": "Episode",
                "last_tmdb_posters_checked_at": posters_checked_at,
                "episode_details": {
                    "series_tmdb_id": series_tmdb_id,
                    "series_title": "Series",
                    "season_num": 1,
                    "episode_num": 1,
                },
            },
            "watch_providers": [],
            "posters": posters,
        }


if __name__ == "__main__":
    unittest.main()
