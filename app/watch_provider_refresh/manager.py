"""Qt lifecycle management for background watch-provider refresh jobs."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QObject, QThreadPool, Signal

from .worker import (
    _CancellationToken,
    _WatchProviderRefreshWorker,
    _WorkerSignals,
)


@dataclass
class _ActiveJob:
    token: _CancellationToken
    worker: _WatchProviderRefreshWorker
    signals: _WorkerSignals


class WatchProviderRefreshManager(QObject):
    """Own and fan out application-lifetime provider network jobs."""

    succeeded = Signal(str, object)
    failed = Signal(str, object)
    cancelled = Signal(str, object)
    finished = Signal(str, object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__(parent)
        self._thread_pool = thread_pool or QThreadPool(self)
        self._jobs: dict[str, _ActiveJob] = {}
        self._lock = RLock()

    def start_refresh(self, media_id: int, match: Mapping) -> str:
        if (
            not isinstance(media_id, int)
            or isinstance(media_id, bool)
            or media_id < 1
        ):
            raise ValueError("Watch-provider refresh requires an existing media id.")

        if not isinstance(match, Mapping):
            raise TypeError("match must be a mapping")

        match_copy = deepcopy(dict(match))
        with self._lock:
            job_id = uuid4().hex
            token = _CancellationToken()
            signals = _WorkerSignals()
            worker = _WatchProviderRefreshWorker(
                job_id=job_id,
                media_id=media_id,
                match=match_copy,
                token=token,
                signals=signals,
            )
            signals.succeeded.connect(self._finish_succeeded)
            signals.failed.connect(self._finish_failed)
            signals.cancelled.connect(self._finish_cancelled)
            self._jobs[job_id] = _ActiveJob(
                token=token,
                worker=worker,
                signals=signals,
            )

        self._thread_pool.start(worker)
        return job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)

            if job is None:
                return False

            job.token.cancel()
            return True

    def cancel_all(self) -> int:
        with self._lock:
            jobs = list(self._jobs.values())

        for job in jobs:
            job.token.cancel()

        return len(jobs)

    def _finish_succeeded(self, job_id: str, payload: object) -> None:
        self._finish(job_id, "succeeded", payload)

    def _finish_failed(self, job_id: str, payload: object) -> None:
        self._finish(job_id, "failed", payload)

    def _finish_cancelled(self, job_id: str, payload: object) -> None:
        self._finish(job_id, "cancelled", payload)

    def _finish(self, job_id: str, status: str, payload: object) -> None:
        with self._lock:
            job = self._jobs.pop(job_id, None)

            if job is None:
                return

        plain_payload = deepcopy(payload)

        if status == "succeeded":
            self.succeeded.emit(job_id, plain_payload)
        elif status == "failed":
            self.failed.emit(job_id, plain_payload)
        else:
            self.cancelled.emit(job_id, plain_payload)

        self.finished.emit(
            job_id,
            {
                "status": status,
                "payload": plain_payload,
            },
        )


_watch_provider_refresh_manager: WatchProviderRefreshManager | None = None


def get_watch_provider_refresh_manager() -> WatchProviderRefreshManager:
    global _watch_provider_refresh_manager

    application = QCoreApplication.instance()

    if application is None:
        raise RuntimeError(
            "WatchProviderRefreshManager requires an active QCoreApplication."
        )

    if _watch_provider_refresh_manager is None:
        _watch_provider_refresh_manager = WatchProviderRefreshManager(
            parent=application
        )
        application.aboutToQuit.connect(
            _watch_provider_refresh_manager.cancel_all
        )
        _watch_provider_refresh_manager.destroyed.connect(
            _clear_watch_provider_refresh_manager
        )

    return _watch_provider_refresh_manager


def _clear_watch_provider_refresh_manager(*_args: object) -> None:
    global _watch_provider_refresh_manager
    _watch_provider_refresh_manager = None
