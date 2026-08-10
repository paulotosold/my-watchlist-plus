"""Qt lifecycle management for background TMDB metadata refresh jobs."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QObject, QThreadPool, Signal

from .worker import (
    _CancellationToken,
    _MetadataRefreshWorker,
    _to_plain_data,
    _WorkerSignals,
)


@dataclass
class _ActiveJob:
    identity: tuple[Any, ...]
    token: _CancellationToken
    worker: _MetadataRefreshWorker
    signals: _WorkerSignals


class MetadataRefreshManager(QObject):
    """Own and fan out application-lifetime metadata refresh jobs."""

    progress = Signal(str, object)
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
        self._jobs_by_identity: dict[tuple[Any, ...], str] = {}
        self._lock = RLock()

    def start_refresh(
        self,
        media_id: int | None,
        match: Mapping[str, Any],
    ) -> str:
        """Start a refresh, or return the active job for the same media."""
        if not isinstance(match, Mapping):
            raise TypeError("match must be a mapping")

        match_copy = deepcopy(dict(match))
        identity = _media_identity(media_id, match_copy)

        with self._lock:
            existing_job_id = self._jobs_by_identity.get(identity)

            if existing_job_id is not None:
                return existing_job_id

            job_id = uuid4().hex
            token = _CancellationToken()
            signals = _WorkerSignals()
            worker = _MetadataRefreshWorker(
                job_id=job_id,
                media_id=media_id,
                match=match_copy,
                token=token,
                signals=signals,
            )
            signals.progress.connect(self._forward_progress)
            signals.succeeded.connect(self._finish_succeeded)
            signals.failed.connect(self._finish_failed)
            signals.cancelled.connect(self._finish_cancelled)
            self._jobs[job_id] = _ActiveJob(
                identity=identity,
                token=token,
                worker=worker,
                signals=signals,
            )
            self._jobs_by_identity[identity] = job_id

        self._thread_pool.start(worker)
        return job_id

    def cancel_refresh(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)

            if job is None:
                return False

            job.token.cancel()
            return True

    def cancel(self, job_id: str) -> bool:
        """Convenience alias for callers that retain only a job ID."""
        return self.cancel_refresh(job_id)

    def cancel_all(self) -> int:
        with self._lock:
            jobs = list(self._jobs.values())

        for job in jobs:
            job.token.cancel()

        return len(jobs)

    def active_job_id(
        self,
        media_id: int | None,
        match: Mapping[str, Any],
    ) -> str | None:
        identity = _media_identity(media_id, match)

        with self._lock:
            return self._jobs_by_identity.get(identity)

    def _forward_progress(self, job_id: str, payload: object) -> None:
        with self._lock:
            active = job_id in self._jobs

        if active:
            self.progress.emit(job_id, _to_plain_data(payload))

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

            self._jobs_by_identity.pop(job.identity, None)

        plain_payload = _to_plain_data(payload)

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


def _media_identity(
    media_id: int | None,
    match: Mapping[str, Any],
) -> tuple[Any, ...]:
    if media_id is not None:
        return ("media_id", media_id)

    resolved_match = match

    if match.get("status") is not None:
        resolved_match = match.get("match")

    if not isinstance(resolved_match, Mapping):
        raise ValueError("A new-media refresh requires a resolved TMDB match.")

    media_type = resolved_match.get("media_type")
    tmdb_id = resolved_match.get("tmdb_id")

    if media_type not in {"movie", "series", "episode"} or tmdb_id is None:
        raise ValueError(
            "A new-media refresh requires media_type and tmdb_id."
        )

    return ("tmdb", media_type, tmdb_id)


_metadata_refresh_manager: MetadataRefreshManager | None = None


def get_metadata_refresh_manager() -> MetadataRefreshManager:
    """Return the singleton manager owned by the active Qt application."""
    global _metadata_refresh_manager

    application = QCoreApplication.instance()

    if application is None:
        raise RuntimeError(
            "MetadataRefreshManager requires an active QCoreApplication."
        )

    if _metadata_refresh_manager is None:
        _metadata_refresh_manager = MetadataRefreshManager(parent=application)
        application.aboutToQuit.connect(_metadata_refresh_manager.cancel_all)
        _metadata_refresh_manager.destroyed.connect(
            _clear_metadata_refresh_manager
        )

    return _metadata_refresh_manager


def _clear_metadata_refresh_manager(*_args: object) -> None:
    global _metadata_refresh_manager
    _metadata_refresh_manager = None
