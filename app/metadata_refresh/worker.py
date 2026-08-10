"""Background execution for explicit TMDB metadata refreshes.

The worker deliberately separates the network and database phases. TMDB is
fully fetched before a connection is opened; once the write transaction starts,
it is allowed to finish atomically even if the caller subsequently cancels.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
import sqlite3
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal

from app import media_repository, tmdb
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
            snapshot = tmdb.get_tmdb_metadata_refresh_snapshot(
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
                # possible. A non-plain payload must never turn a committed
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
