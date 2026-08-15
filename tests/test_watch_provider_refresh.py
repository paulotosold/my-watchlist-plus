import os
from copy import deepcopy
from threading import Event, get_ident
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

import app.watch_provider_refresh as watch_provider_refresh
import app.watch_provider_refresh.worker as watch_provider_refresh_worker


PROVIDERS = [{
    "provider_tmdb_id": 8,
    "provider_name": "Netflix",
    "country_code": "AT",
    "access_type": "flatrate",
}]


class WatchProviderRefreshManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self.manager = watch_provider_refresh.WatchProviderRefreshManager(
            thread_pool=self.pool
        )

    def tearDown(self):
        self.manager.cancel_all()
        self.assertTrue(self.pool.waitForDone(3000))
        self.application.processEvents()

    def test_fetch_runs_in_background_and_emits_plain_success_payload(self):
        fetch_thread_ids = []
        success_spy = QSignalSpy(self.manager.succeeded)
        finished_spy = QSignalSpy(self.manager.finished)

        def fetch(match):
            fetch_thread_ids.append(get_ident())
            self.assertEqual(
                match,
                {"media_type": "movie", "tmdb_id": 7},
            )
            return deepcopy(PROVIDERS)

        with patch.object(
            watch_provider_refresh_worker.tmdb,
            "get_tmdb_media_watch_providers",
            side_effect=fetch,
        ), patch.object(
            watch_provider_refresh_worker,
            "current_freshness_timestamp",
            return_value="2026-08-14 12:00:00",
        ):
            job_id = self.manager.start_refresh(
                42,
                {"media_type": "movie", "tmdb_id": 7},
            )
            self._wait_for(success_spy)

        self.assertNotEqual(fetch_thread_ids, [get_ident()])
        self.assertEqual(
            success_spy.at(0),
            [
                job_id,
                {
                    "media_id": 42,
                    "watch_providers": PROVIDERS,
                    "checked_at": "2026-08-14 12:00:00",
                },
            ],
        )
        self.assertEqual(finished_spy.count(), 1)
        self.assertEqual(finished_spy.at(0)[1]["status"], "succeeded")

    def test_same_media_jobs_are_independent(self):
        fetch_started = Event()
        release_fetch = Event()
        success_spy = QSignalSpy(self.manager.succeeded)
        fetch_count = 0

        def fetch(_match):
            nonlocal fetch_count
            fetch_count += 1
            fetch_started.set()
            self.assertTrue(release_fetch.wait(2))
            return deepcopy(PROVIDERS)

        with patch.object(
            watch_provider_refresh_worker.tmdb,
            "get_tmdb_media_watch_providers",
            side_effect=fetch,
        ):
            first_job_id = self.manager.start_refresh(
                42,
                {"media_type": "movie", "tmdb_id": 7},
            )
            self.assertTrue(fetch_started.wait(2))
            second_job_id = self.manager.start_refresh(
                42,
                {"media_type": "movie", "tmdb_id": 7},
            )
            release_fetch.set()
            self._wait_for(success_spy, expected_count=2)

        self.assertNotEqual(first_job_id, second_job_id)
        self.assertEqual(fetch_count, 2)
        self.assertEqual(success_spy.count(), 2)

    def test_cancelled_fetch_never_emits_success(self):
        fetch_started = Event()
        release_fetch = Event()
        cancelled_spy = QSignalSpy(self.manager.cancelled)
        success_spy = QSignalSpy(self.manager.succeeded)

        def fetch(_match):
            fetch_started.set()
            self.assertTrue(release_fetch.wait(2))
            return deepcopy(PROVIDERS)

        with patch.object(
            watch_provider_refresh_worker.tmdb,
            "get_tmdb_media_watch_providers",
            side_effect=fetch,
        ):
            job_id = self.manager.start_refresh(
                42,
                {"media_type": "movie", "tmdb_id": 7},
            )
            self.assertTrue(fetch_started.wait(2))
            self.assertTrue(self.manager.cancel(job_id))
            release_fetch.set()
            self._wait_for(cancelled_spy)

        self.assertEqual(
            cancelled_spy.at(0),
            [job_id, {"media_id": 42}],
        )
        self.assertEqual(success_spy.count(), 0)
        self.assertFalse(self.manager.cancel(job_id))

    def test_fetch_failure_emits_plain_error(self):
        failed_spy = QSignalSpy(self.manager.failed)

        with patch.object(
            watch_provider_refresh_worker.tmdb,
            "get_tmdb_media_watch_providers",
            side_effect=ConnectionError("offline"),
        ):
            self.manager.start_refresh(
                42,
                {"media_type": "movie", "tmdb_id": 7},
            )
            self._wait_for(failed_spy)

        self.assertEqual(
            failed_spy.at(0)[1],
            {"message": "offline", "type": "ConnectionError"},
        )

    def test_new_media_without_database_id_is_supported(self):
        success_spy = QSignalSpy(self.manager.succeeded)

        with patch.object(
            watch_provider_refresh_worker.tmdb,
            "get_tmdb_media_watch_providers",
            return_value=deepcopy(PROVIDERS),
        ), patch.object(
            watch_provider_refresh_worker,
            "current_freshness_timestamp",
            return_value="2026-08-15 12:00:00",
        ):
            job_id = self.manager.start_refresh(
                None,
                {"media_type": "movie", "tmdb_id": 7},
            )
            self._wait_for(success_spy)

        self.assertEqual(success_spy.at(0)[0], job_id)
        self.assertIsNone(success_spy.at(0)[1]["media_id"])

    def test_rejects_an_invalid_media_id(self):
        with self.assertRaisesRegex(ValueError, "valid media id"):
            self.manager.start_refresh(
                0,
                {"media_type": "movie", "tmdb_id": 7},
            )

    def test_singleton_is_owned_by_qt_application(self):
        first = watch_provider_refresh.get_watch_provider_refresh_manager()
        second = watch_provider_refresh.get_watch_provider_refresh_manager()

        self.assertIs(first, second)
        self.assertIs(first.parent(), self.application)

    def _wait_for(self, spy, timeout=3000, expected_count=1):
        deadline = time.monotonic() + (timeout / 1000)

        while spy.count() < expected_count and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)

        self.application.processEvents()
        self.assertGreaterEqual(
            spy.count(),
            expected_count,
            "Timed out waiting for Qt signal",
        )


if __name__ == "__main__":
    unittest.main()
