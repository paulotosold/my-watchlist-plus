"""Background network fetches for TMDB watch-provider refreshes."""

from __future__ import annotations

from copy import deepcopy
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

import app.tmdb as tmdb
from app.tmdb import current_freshness_timestamp


class _CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class _WorkerSignals(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    cancelled = Signal(str, object)


class _WatchProviderRefreshWorker(QRunnable):
    def __init__(
        self,
        *,
        job_id: str,
        media_id: int,
        match: dict,
        token: _CancellationToken,
        signals: _WorkerSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._job_id = job_id
        self._media_id = media_id
        self._match = deepcopy(match)
        self._token = token
        self._signals = signals

    def run(self) -> None:
        try:
            providers = tmdb.get_tmdb_media_watch_providers(
                deepcopy(self._match)
            )

            if self._token.is_cancelled():
                self._emit_cancelled()
                return

            self._signals.succeeded.emit(
                self._job_id,
                {
                    "media_id": self._media_id,
                    "watch_providers": deepcopy(providers),
                    "checked_at": current_freshness_timestamp(),
                },
            )
        except Exception as exc:  # noqa: BLE001 - errors cross a Qt signal boundary
            if self._token.is_cancelled():
                self._emit_cancelled()
                return

            self._signals.failed.emit(
                self._job_id,
                {
                    "message": str(exc) or type(exc).__name__,
                    "type": type(exc).__name__,
                },
            )

    def _emit_cancelled(self) -> None:
        self._signals.cancelled.emit(
            self._job_id,
            {"media_id": self._media_id},
        )
