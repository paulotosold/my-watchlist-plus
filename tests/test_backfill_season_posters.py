import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import MagicMock, call, patch


os.environ.setdefault("OPENAI_API_KEY", "test-key")

import scripts.backfill_season_posters as backfill_script
from db.connection import apply_database_schema


CHECKED_AT = "2026-07-17 12:34:56"
POSTER_DIR = Path("/tmp/test-backfill-season-posters")


class BackfillSeasonPostersTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_dry_run_reports_missing_without_downloading_or_writing(self):
        series_id = self._insert_series(
            101,
            "Dry Run Series",
            posters_checked_at="old-check",
        )
        self.conn.commit()

        with patch.object(
            backfill_script.tmdb,
            "get_tmdb_series_primary_season_posters",
            return_value=[self._poster(101, 1, "season-one.jpg")],
        ), patch.object(
            backfill_script.poster_storage,
            "download_missing_draft_posters",
        ) as download_mock, patch.object(
            backfill_script.media_repository,
            "insert_missing_series_season_posters",
        ) as insert_mock:
            results = backfill_script.backfill_season_posters(
                self.conn,
                apply=False,
                poster_dir=POSTER_DIR,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "ok")
        self.assertEqual(results[0]["missing_count"], 1)
        self.assertEqual(results[0]["inserted_count"], 0)
        download_mock.assert_not_called()
        insert_mock.assert_not_called()
        self.assertEqual(self._season_poster_rows(series_id), [])
        self.assertEqual(self._posters_checked_at(series_id), "old-check")

    def test_apply_preserves_existing_inserts_missing_and_is_idempotent(self):
        series_id = self._insert_series(202, "Apply Series")
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
            VALUES (?, 1, 'user-season-one.jpg', 'user', 'selected', 1)
            """,
            (series_id,),
        )
        self.conn.commit()
        canonical_posters = [
            self._poster(202, 1, "tmdb-season-one.jpg"),
            self._poster(202, 2, "tmdb-season-two.jpg"),
        ]

        def fake_download(media_draft, **_kwargs):
            filenames = [
                poster["filename"]
                for poster in media_draft.get("posters", [])
            ]
            return {"downloaded": filenames, "skipped": [], "failed": []}

        with patch.object(
            backfill_script.tmdb,
            "get_tmdb_series_primary_season_posters",
            return_value=canonical_posters,
        ), patch.object(
            backfill_script,
            "current_freshness_timestamp",
            return_value=CHECKED_AT,
        ), patch.object(
            backfill_script.poster_storage,
            "download_missing_draft_posters",
            side_effect=fake_download,
        ):
            first_results = backfill_script.backfill_season_posters(
                self.conn,
                apply=True,
                poster_dir=POSTER_DIR,
            )
            second_results = backfill_script.backfill_season_posters(
                self.conn,
                apply=True,
                poster_dir=POSTER_DIR,
            )

        self.assertEqual(first_results[0]["missing_count"], 1)
        self.assertEqual(first_results[0]["inserted_count"], 1)
        self.assertEqual(
            first_results[0]["poster_downloads"]["downloaded"],
            ["tmdb-season-two.jpg"],
        )
        self.assertEqual(second_results[0]["missing_count"], 0)
        self.assertEqual(second_results[0]["inserted_count"], 0)
        self.assertEqual(second_results[0]["poster_downloads"]["downloaded"], [])
        self.assertEqual(
            self._season_poster_rows(series_id),
            [
                {
                    "season_num": 1,
                    "filename": "user-season-one.jpg",
                    "source": "user",
                    "curation_status": "selected",
                    "is_default": 1,
                },
                {
                    "season_num": 2,
                    "filename": "tmdb-season-two.jpg",
                    "source": "tmdb",
                    "curation_status": "pending",
                    "is_default": 0,
                },
            ],
        )
        self.assertEqual(self._posters_checked_at(series_id), CHECKED_AT)

    def test_failure_for_one_series_does_not_prevent_the_next_series(self):
        failed_series_id = self._insert_series(301, "A Failed Series")
        successful_series_id = self._insert_series(302, "B Successful Series")
        self.conn.commit()

        def fake_fetch(series_tmdb_id):
            if series_tmdb_id == 301:
                raise RuntimeError("TMDB unavailable")

            return [self._poster(302, 1, "successful.jpg")]

        with patch.object(
            backfill_script.tmdb,
            "get_tmdb_series_primary_season_posters",
            side_effect=fake_fetch,
        ), patch.object(
            backfill_script,
            "current_freshness_timestamp",
            return_value=CHECKED_AT,
        ), patch.object(
            backfill_script.poster_storage,
            "download_missing_draft_posters",
            return_value={
                "downloaded": ["successful.jpg"],
                "skipped": [],
                "failed": [],
            },
        ):
            results = backfill_script.backfill_season_posters(
                self.conn,
                apply=True,
                poster_dir=POSTER_DIR,
            )

        self.assertEqual([result["status"] for result in results], ["failed", "ok"])
        self.assertIn("TMDB unavailable", results[0]["error"])
        self.assertEqual(self._season_poster_rows(failed_series_id), [])
        self.assertEqual(
            self._season_poster_rows(successful_series_id)[0]["filename"],
            "successful.jpg",
        )
        self.assertIsNone(self._posters_checked_at(failed_series_id))
        self.assertEqual(self._posters_checked_at(successful_series_id), CHECKED_AT)

    def test_download_failure_does_not_persist_or_advance_timestamp(self):
        series_id = self._insert_series(
            401,
            "Retry Series",
            posters_checked_at="parent-old",
        )
        episode_id = self._insert_episode(
            series_id,
            402,
            posters_checked_at="episode-old",
        )
        self.conn.commit()
        poster = self._poster(401, 1, "retry.jpg")
        failed_download = {
            "downloaded": [],
            "skipped": [],
            "failed": [{"filename": "retry.jpg", "error": "network error"}],
        }
        successful_download = {
            "downloaded": ["retry.jpg"],
            "skipped": [],
            "failed": [],
        }

        with patch.object(
            backfill_script.tmdb,
            "get_tmdb_series_primary_season_posters",
            return_value=[poster],
        ), patch.object(
            backfill_script,
            "current_freshness_timestamp",
            return_value=CHECKED_AT,
        ) as timestamp_mock, patch.object(
            backfill_script.poster_storage,
            "download_missing_draft_posters",
            side_effect=[failed_download, successful_download],
        ):
            failed_results = backfill_script.backfill_season_posters(
                self.conn,
                apply=True,
                poster_dir=POSTER_DIR,
            )

            self.assertEqual(failed_results[0]["status"], "failed")
            self.assertEqual(self._season_poster_rows(series_id), [])
            self.assertEqual(self._posters_checked_at(series_id), "parent-old")
            self.assertEqual(self._posters_checked_at(episode_id), "episode-old")

            successful_results = backfill_script.backfill_season_posters(
                self.conn,
                apply=True,
                poster_dir=POSTER_DIR,
            )

        self.assertEqual(successful_results[0]["status"], "ok")
        self.assertEqual(successful_results[0]["inserted_count"], 1)
        self.assertEqual(
            self._season_poster_rows(series_id)[0]["filename"],
            "retry.jpg",
        )
        self.assertEqual(self._posters_checked_at(series_id), CHECKED_AT)
        self.assertEqual(self._posters_checked_at(episode_id), "episode-old")
        timestamp_mock.assert_called_once_with()

    def test_main_returns_failure_if_any_series_fails_and_zero_otherwise(self):
        connection = object()
        connection_context = MagicMock()
        connection_context.__enter__.return_value = connection
        connection_context.__exit__.return_value = False
        failed_results = [
            {"status": "ok"},
            {"status": "failed"},
        ]
        successful_results = [
            {"status": "ok"},
            {"status": "ok"},
        ]

        with patch.object(
            backfill_script,
            "get_connection",
            return_value=connection_context,
        ) as get_connection_mock, patch.object(
            backfill_script,
            "backfill_season_posters",
            side_effect=[failed_results, successful_results],
        ) as backfill_mock, patch.object(
            backfill_script,
            "print_results",
        ) as print_results_mock:
            failed_exit_code = backfill_script.main(["--apply"])
            successful_exit_code = backfill_script.main(["--dry-run"])

        self.assertEqual(failed_exit_code, 1)
        self.assertEqual(successful_exit_code, 0)
        self.assertEqual(get_connection_mock.call_count, 2)
        self.assertEqual(connection_context.__enter__.call_count, 2)
        self.assertEqual(connection_context.__exit__.call_count, 2)
        backfill_mock.assert_has_calls([
            call(connection, apply=True),
            call(connection, apply=False),
        ])
        print_results_mock.assert_has_calls([
            call(failed_results, apply=True),
            call(successful_results, apply=False),
        ])

    def _insert_series(self, tmdb_id, title, posters_checked_at=None):
        cursor = self.conn.execute(
            """
            INSERT INTO media (
                tmdb_id,
                media_type,
                title,
                last_tmdb_posters_checked_at
            )
            VALUES (?, 'series', ?, ?)
            """,
            (tmdb_id, title, posters_checked_at),
        )
        return cursor.lastrowid

    def _insert_episode(self, series_id, tmdb_id, posters_checked_at=None):
        cursor = self.conn.execute(
            """
            INSERT INTO media (
                tmdb_id,
                media_type,
                title,
                last_tmdb_posters_checked_at
            )
            VALUES (?, 'episode', 'Episode', ?)
            """,
            (tmdb_id, posters_checked_at),
        )
        episode_id = cursor.lastrowid
        self.conn.execute(
            """
            INSERT INTO episode_details (
                media_id,
                series_id,
                season_num,
                episode_num
            )
            VALUES (?, ?, 1, 1)
            """,
            (episode_id, series_id),
        )
        return episode_id

    def _poster(self, series_tmdb_id, season_num, filename):
        return {
            "scope": "season",
            "filename": filename,
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False,
            "series_tmdb_id": series_tmdb_id,
            "season_num": season_num,
        }

    def _season_poster_rows(self, series_id):
        rows = self.conn.execute(
            """
            SELECT
                season_num,
                filename,
                source,
                curation_status,
                is_default
            FROM season_posters
            WHERE series_id = ?
            ORDER BY season_num, id
            """,
            (series_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _posters_checked_at(self, media_id):
        return self.conn.execute(
            """
            SELECT last_tmdb_posters_checked_at
            FROM media
            WHERE id = ?
            """,
            (media_id,),
        ).fetchone()[0]


if __name__ == "__main__":
    unittest.main()
