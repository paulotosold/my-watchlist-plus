"""Background orchestration for explicit TMDB metadata refreshes.

The worker deliberately separates the network and database phases.  TMDB is
fully fetched before a connection is opened; once the write transaction starts,
it is allowed to finish atomically even if the caller subsequently cancels.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
import sqlite3
from threading import Event, RLock
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, Signal

from app import media_repository, tmdb_fetcher
from db.connection import get_connection


class _CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class _WorkerSignals(QObject):
    progress = Signal(str, object)
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    cancelled = Signal(str, object)


class _MetadataRefreshWorker(QRunnable):
    def __init__(
        self,
        *,
        job_id: str,
        media_id: int | None,
        match: Mapping[str, Any],
        token: _CancellationToken,
        signals: _WorkerSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._job_id = job_id
        self._media_id = media_id
        self._match = deepcopy(dict(match))
        self._token = token
        self._signals = signals

    def run(self) -> None:
        transaction_started = False
        conn = None

        try:
            snapshot = tmdb_fetcher.get_tmdb_metadata_refresh_snapshot(
                deepcopy(self._match),
                should_cancel=self._token.is_cancelled,
                report_progress=self._report_progress,
            )

            if self._token.is_cancelled():
                self._emit_cancelled()
                return

            plain_snapshot = _to_plain_data(snapshot)
            refresh_result = None
            plain_refresh_result = None

            if self._media_id is not None:
                # Opening a connection is intentionally deferred until every
                # network request has completed successfully.
                if self._token.is_cancelled():
                    self._emit_cancelled()
                    return

                conn = get_connection()

                if self._token.is_cancelled():
                    self._emit_cancelled()
                    return

                conn.execute("BEGIN IMMEDIATE")
                transaction_started = True
                refresh_result = media_repository.apply_metadata_refresh(
                    conn,
                    self._media_id,
                    snapshot,
                )
                # Normalize the repository result while rollback is still
                # possible.  A non-plain payload must never turn a committed
                # refresh into an apparent worker failure.
                plain_refresh_result = _to_plain_data(refresh_result)
                conn.commit()

            payload = {
                "media_id": self._media_id,
                "snapshot": plain_snapshot,
                "refresh_result": plain_refresh_result,
            }
            self._signals.succeeded.emit(self._job_id, payload)
        except Exception as exc:  # noqa: BLE001 - errors cross a Qt signal boundary
            if transaction_started and conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass

            if self._token.is_cancelled() and not transaction_started:
                self._emit_cancelled()
            else:
                self._signals.failed.emit(
                    self._job_id,
                    {
                        "message": str(exc) or type(exc).__name__,
                        "type": type(exc).__name__,
                    },
                )
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _report_progress(self, message: str) -> None:
        if not self._token.is_cancelled():
            self._signals.progress.emit(
                self._job_id,
                {"message": str(message)},
            )

    def _emit_cancelled(self) -> None:
        self._signals.cancelled.emit(
            self._job_id,
            {"media_id": self._media_id},
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


def _to_plain_data(value: Any) -> Any:
    """Copy worker results into signal-safe, SQLite-free structures."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, sqlite3.Row):
        return {key: _to_plain_data(value[key]) for key in value.keys()}

    if isinstance(value, Mapping):
        return {
            _to_plain_data(key): _to_plain_data(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_plain_data(item) for item in value]

    raise TypeError(
        f"Metadata refresh results must contain plain data, got "
        f"{type(value).__name__}."
    )


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
