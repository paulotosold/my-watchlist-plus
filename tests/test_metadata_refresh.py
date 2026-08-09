import os
from concurrent.futures import CancelledError
from copy import deepcopy
from threading import Event
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

import app.metadata_refresh as metadata_refresh


SNAPSHOT = {
    "media_type": "series",
    "tmdb_id": 100,
    "checked_at": "2026-07-13 12:00:00",
    "metadata": {"tmdb_id": 100, "title": "Example"},
    "regular_episodes": [],
    "series_summary": {"season_count": 0, "episode_count": 0},
    "loaded_fields": {
        "metadata": ["title"],
        "regular_episodes": [],
        "series_summary": ["season_count", "episode_count"],
    },
}


class FakeConnection:
    def __init__(self, events):
        self.events = events

    def execute(self, statement):
        self.events.append(statement)
        return self

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def close(self):
        self.events.append("close")


class MetadataRefreshManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self.manager = metadata_refresh.MetadataRefreshManager(
            thread_pool=self.pool
        )

    def tearDown(self):
        self.manager.cancel_all()
        self.assertTrue(self.pool.waitForDone(3000))
        self.application.processEvents()

    def test_existing_media_fetches_before_atomic_database_apply(self):
        events = []
        conn = FakeConnection(events)
        success_spy = QSignalSpy(self.manager.succeeded)
        progress_spy = QSignalSpy(self.manager.progress)
        finished_spy = QSignalSpy(self.manager.finished)

        def fetch(match, should_cancel, report_progress):
            events.append("fetch")
            self.assertFalse(should_cancel())
            report_progress("Fetching series metadata")
            return deepcopy(SNAPSHOT)

        def apply_refresh(received_conn, media_id, snapshot):
            events.append("apply")
            self.assertIs(received_conn, conn)
            self.assertEqual(media_id, 8)
            self.assertEqual(snapshot, SNAPSHOT)
            return {"created": 2, "row": None}

        with patch.object(
            metadata_refresh.tmdb,
            "get_tmdb_metadata_refresh_snapshot",
            side_effect=fetch,
        ), patch.object(
            metadata_refresh,
            "get_connection",
            side_effect=lambda: events.append("connect") or conn,
        ), patch.object(
            metadata_refresh.media_repository,
            "apply_metadata_refresh",
            side_effect=apply_refresh,
        ):
            job_id = self.manager.start_refresh(
                8,
                {"media_type": "series", "tmdb_id": 100},
            )
            self._wait_for(success_spy)

        self.assertEqual(
            events,
            ["fetch", "connect", "BEGIN IMMEDIATE", "apply", "commit", "close"],
        )
        self.assertEqual(progress_spy.at(0), [
            job_id,
            {"message": "Fetching series metadata"},
        ])
        self.assertEqual(success_spy.at(0)[0], job_id)
        self.assertEqual(success_spy.at(0)[1]["media_id"], 8)
        self.assertEqual(success_spy.at(0)[1]["snapshot"], SNAPSHOT)
        self.assertEqual(
            success_spy.at(0)[1]["refresh_result"],
            {"created": 2, "row": None},
        )
        self.assertEqual(finished_spy.count(), 1)
        self.assertEqual(finished_spy.at(0)[1]["status"], "succeeded")

    def test_new_media_returns_snapshot_without_opening_database(self):
        success_spy = QSignalSpy(self.manager.succeeded)
        connection = Mock()
        apply_refresh = Mock()

        with patch.object(
            metadata_refresh.tmdb,
            "get_tmdb_metadata_refresh_snapshot",
            return_value=deepcopy(SNAPSHOT),
        ), patch.object(
            metadata_refresh,
            "get_connection",
            connection,
        ), patch.object(
            metadata_refresh.media_repository,
            "apply_metadata_refresh",
            apply_refresh,
        ):
            self.manager.start_refresh(
                None,
                {"media_type": "series", "tmdb_id": 100},
            )
            self._wait_for(success_spy)

        connection.assert_not_called()
        apply_refresh.assert_not_called()
        payload = success_spy.at(0)[1]
        self.assertIsNone(payload["media_id"])
        self.assertEqual(payload["snapshot"], SNAPSHOT)
        self.assertIsNone(payload["refresh_result"])

    def test_same_media_identity_reuses_active_job(self):
        fetch_started = Event()
        release_fetch = Event()
        success_spy = QSignalSpy(self.manager.succeeded)

        def fetch(_match, should_cancel, report_progress):
            del should_cancel, report_progress
            fetch_started.set()
            self.assertTrue(release_fetch.wait(2))
            return deepcopy(SNAPSHOT)

        with patch.object(
            metadata_refresh.tmdb,
            "get_tmdb_metadata_refresh_snapshot",
            side_effect=fetch,
        ):
            first_job_id = self.manager.start_refresh(
                None,
                {"media_type": "series", "tmdb_id": 100},
            )
            self.assertTrue(fetch_started.wait(2))
            second_job_id = self.manager.start_refresh(
                None,
                {
                    "status": "resolved",
                    "match": {"media_type": "series", "tmdb_id": 100},
                },
            )
            release_fetch.set()
            self._wait_for(success_spy)

        self.assertEqual(first_job_id, second_job_id)
        self.assertEqual(success_spy.count(), 1)

    def test_cancel_before_database_phase_emits_cancelled(self):
        fetch_started = Event()
        cancelled_spy = QSignalSpy(self.manager.cancelled)
        failed_spy = QSignalSpy(self.manager.failed)
        connection = Mock()

        def fetch(_match, should_cancel, report_progress):
            del report_progress
            fetch_started.set()

            while not should_cancel():
                Event().wait(0.005)

            raise CancelledError()

        with patch.object(
            metadata_refresh.tmdb,
            "get_tmdb_metadata_refresh_snapshot",
            side_effect=fetch,
        ), patch.object(
            metadata_refresh,
            "get_connection",
            connection,
        ):
            job_id = self.manager.start_refresh(
                8,
                {"media_type": "series", "tmdb_id": 100},
            )
            self.assertTrue(fetch_started.wait(2))
            self.assertTrue(self.manager.cancel(job_id))
            self._wait_for(cancelled_spy)

        connection.assert_not_called()
        self.assertEqual(cancelled_spy.at(0), [job_id, {"media_id": 8}])
        self.assertEqual(failed_spy.count(), 0)
        self.assertFalse(self.manager.cancel(job_id))

    def test_cancel_after_transaction_begins_does_not_interrupt_commit(self):
        apply_started = Event()
        release_apply = Event()
        events = []
        conn = FakeConnection(events)
        success_spy = QSignalSpy(self.manager.succeeded)
        cancelled_spy = QSignalSpy(self.manager.cancelled)

        def apply_refresh(_conn, _media_id, _snapshot):
            events.append("apply")
            apply_started.set()
            self.assertTrue(release_apply.wait(2))
            return {"updated": 1}

        with patch.object(
            metadata_refresh.tmdb,
            "get_tmdb_metadata_refresh_snapshot",
            return_value=deepcopy(SNAPSHOT),
        ), patch.object(
            metadata_refresh,
            "get_connection",
            return_value=conn,
        ), patch.object(
            metadata_refresh.media_repository,
            "apply_metadata_refresh",
            side_effect=apply_refresh,
        ):
            job_id = self.manager.start_refresh(
                8,
                {"media_type": "series", "tmdb_id": 100},
            )
            self.assertTrue(apply_started.wait(2))
            self.assertTrue(self.manager.cancel(job_id))
            release_apply.set()
            self._wait_for(success_spy)

        self.assertIn("commit", events)
        self.assertNotIn("rollback", events)
        self.assertEqual(cancelled_spy.count(), 0)

    def test_apply_failure_rolls_back_and_emits_plain_error(self):
        events = []
        conn = FakeConnection(events)
        failed_spy = QSignalSpy(self.manager.failed)

        with patch.object(
            metadata_refresh.tmdb,
            "get_tmdb_metadata_refresh_snapshot",
            return_value=deepcopy(SNAPSHOT),
        ), patch.object(
            metadata_refresh,
            "get_connection",
            return_value=conn,
        ), patch.object(
            metadata_refresh.media_repository,
            "apply_metadata_refresh",
            side_effect=ValueError("identity conflict"),
        ):
            self.manager.start_refresh(
                8,
                {"media_type": "series", "tmdb_id": 100},
            )
            self._wait_for(failed_spy)

        self.assertEqual(
            failed_spy.at(0)[1],
            {"message": "identity conflict", "type": "ValueError"},
        )
        self.assertEqual(
            events,
            ["BEGIN IMMEDIATE", "rollback", "close"],
        )

    def test_singleton_is_owned_by_qt_application(self):
        first = metadata_refresh.get_metadata_refresh_manager()
        second = metadata_refresh.get_metadata_refresh_manager()

        self.assertIs(first, second)
        self.assertIs(first.parent(), self.application)

    def _wait_for(self, spy, timeout=3000):
        deadline = time.monotonic() + (timeout / 1000)

        while spy.count() == 0 and time.monotonic() < deadline:
            # QSignalSpy.wait() holds the Python GIL on some PySide releases,
            # which prevents a Python QRunnable from entering run().
            self.application.processEvents()
            time.sleep(0.005)

        self.application.processEvents()
        self.assertGreater(spy.count(), 0, "Timed out waiting for Qt signal")


if __name__ == "__main__":
    unittest.main()
