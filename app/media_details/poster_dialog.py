"""Poster-curation dialog used by Media Details."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import app.tmdb as tmdb
from app.find_media.selection_dialog import TmdbPosterLoader
from app.paths import MEDIA_POSTERS_DIR
from app.tmdb import current_freshness_timestamp

from .formatters import build_tmdb_match_from_metadata


MANAGE_POSTERS_WIDTH = 1050
MANAGE_POSTERS_HEIGHT = 720
MANAGE_POSTERS_COLUMNS = 5
MANAGE_POSTER_WIDTH = 185
MANAGE_POSTER_HEIGHT = 278
MANAGE_POSTER_PREVIEW_SIZE = "w342"
LARGE_POSTER_PREVIEW_SIZE = "w780"
POSTER_PREVIEW_WIDTH = 520
POSTER_PREVIEW_HEIGHT = 680
POSTER_MANAGEMENT_KEY = "_poster_management"


class _PosterDiscoverySignals(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, object)


class _PosterDiscoveryWorker(QRunnable):
    def __init__(self, job_id, match, cancelled, signals):
        super().__init__()
        self.setAutoDelete(True)
        self.job_id = job_id
        self.match = deepcopy(match)
        self.cancelled = cancelled
        self.signals = signals

    def run(self):
        try:
            posters = tmdb.get_tmdb_media_posters(self.match)
            if self.cancelled.is_set():
                return
            self.signals.succeeded.emit(
                self.job_id,
                {
                    "posters": deepcopy(posters),
                    "checked_at": current_freshness_timestamp(),
                },
            )
        except Exception as exc:  # noqa: BLE001 - crosses a Qt signal boundary
            if not self.cancelled.is_set():
                self.signals.failed.emit(
                    self.job_id,
                    {"message": str(exc) or type(exc).__name__},
                )


class PosterDiscoveryManager(QObject):
    """Run poster discovery outside the GUI thread."""

    succeeded = Signal(str, object)
    failed = Signal(str, object)
    finished = Signal(str, object)

    def __init__(self, parent=None, thread_pool=None):
        super().__init__(parent)
        self.thread_pool = thread_pool or QThreadPool(self)
        self.jobs = {}

    def start(self, match):
        job_id = uuid4().hex
        cancelled = Event()
        signals = _PosterDiscoverySignals()
        worker = _PosterDiscoveryWorker(job_id, match, cancelled, signals)
        signals.succeeded.connect(self._succeeded)
        signals.failed.connect(self._failed)
        self.jobs[job_id] = (cancelled, worker, signals)
        self.thread_pool.start(worker)
        return job_id

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job is None:
            return False
        job[0].set()
        self.jobs.pop(job_id, None)
        self.finished.emit(job_id, {"status": "cancelled"})
        return True

    def _succeeded(self, job_id, payload):
        if self.jobs.pop(job_id, None) is None:
            return
        self.succeeded.emit(job_id, deepcopy(payload))
        self.finished.emit(job_id, {"status": "succeeded"})

    def _failed(self, job_id, payload):
        if self.jobs.pop(job_id, None) is None:
            return
        self.failed.emit(job_id, deepcopy(payload))
        self.finished.emit(job_id, {"status": "failed"})


class ClickablePosterLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class PosterPreviewDialog(QDialog):
    """Show one poster at a larger size without changing its selection."""

    def __init__(self, parent, poster, *, preview_loader=None):
        super().__init__(parent)
        self.poster = deepcopy(poster)
        self.preview_loader = preview_loader or TmdbPosterLoader(
            self,
            image_size=LARGE_POSTER_PREVIEW_SIZE,
        )
        self.remote_url = None
        self.source_pixmap = None

        self.setWindowTitle("Poster Preview")
        self.setModal(True)
        self.setFixedSize(POSTER_PREVIEW_WIDTH, POSTER_PREVIEW_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.image_label = QLabel("Loading…", self)
        self.image_label.setObjectName("largePosterPreview")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton("Close", self)
        self.close_button.setFixedSize(100, 32)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        footer.addStretch()
        layout.addLayout(footer)

        self.setStyleSheet("""
            QDialog { background-color: #f1f1f1; }
            QLabel#largePosterPreview {
                color: #707070;
                background-color: #e3e3e3;
            }
            QPushButton {
                background-color: white;
                color: black;
                border: 1px solid #bcbcbc;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f2f2f2; }
        """)
        self._load_poster()

    def _load_poster(self):
        local_path = _poster_local_path(self.poster)
        if local_path is not None:
            pixmap = QPixmap(str(local_path))
            self._set_pixmap(pixmap if not pixmap.isNull() else None)
            return

        if self.poster.get("source", "tmdb") != "tmdb":
            self._set_pixmap(None)
            return

        filename = self.poster.get("filename")
        self.preview_loader.poster_loaded.connect(self._poster_loaded)
        url_for = getattr(self.preview_loader, "url_for", None)
        if callable(url_for):
            self.remote_url = url_for(filename)
        requested_url = self.preview_loader.request(filename)
        if self.remote_url is None:
            self.remote_url = requested_url
        if self.remote_url is None:
            self._set_pixmap(None)

    def _poster_loaded(self, url, pixmap):
        if url == self.remote_url:
            self._set_pixmap(pixmap)

    def _set_pixmap(self, pixmap):
        self.source_pixmap = pixmap
        if pixmap is None or pixmap.isNull():
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("Preview unavailable")
            return
        self.image_label.setText("")
        QTimer.singleShot(0, self._render_pixmap)

    def _render_pixmap(self):
        if self.source_pixmap is None or self.source_pixmap.isNull():
            return
        self.image_label.setPixmap(
            self.source_pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._render_pixmap()


class PosterCard(QWidget):
    keep_changed = Signal(str, bool)
    default_clicked = Signal(str)
    preview_requested = Signal(object)

    def __init__(self, poster, key, preview_loader, parent=None):
        super().__init__(parent)
        self.poster = poster
        self.key = key
        self.preview_loader = preview_loader
        self.remote_url = None
        self.setFixedWidth(MANAGE_POSTER_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.preview = ClickablePosterLabel(self)
        self.preview.setObjectName("managePosterPreview")
        self.preview.setFixedSize(MANAGE_POSTER_WIDTH, MANAGE_POSTER_HEIGHT)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview.setToolTip("Open larger preview")
        self.preview.clicked.connect(
            lambda: self.preview_requested.emit(deepcopy(self.poster))
        )
        layout.addWidget(self.preview)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(0)
        self.keep_checkbox = QCheckBox("Keep", self)
        self.default_radio = QRadioButton("Default", self)
        self.default_radio.setAutoExclusive(False)
        controls.addWidget(self.keep_checkbox)
        controls.addStretch()
        controls.addWidget(self.default_radio)
        layout.addLayout(controls)

        self.keep_checkbox.toggled.connect(
            lambda checked: self.keep_changed.emit(self.key, checked)
        )
        self.default_radio.clicked.connect(
            lambda _checked=False: self.default_clicked.emit(self.key)
        )
        self._load_preview()

    def set_state(self, kept, is_default):
        self.keep_checkbox.blockSignals(True)
        self.keep_checkbox.setChecked(kept)
        self.keep_checkbox.blockSignals(False)
        self.default_radio.blockSignals(True)
        self.default_radio.setChecked(is_default)
        self.default_radio.blockSignals(False)
        self.default_radio.setVisible(kept)

    def _load_preview(self):
        local_path = _poster_local_path(self.poster)
        if local_path is not None:
            pixmap = QPixmap(str(local_path))
            self._set_pixmap(pixmap if not pixmap.isNull() else None)
            return

        if self.poster.get("source", "tmdb") != "tmdb":
            self._set_pixmap(None)
            return

        filename = self.poster.get("filename")
        self.preview.setText("Loading…")
        self.preview_loader.poster_loaded.connect(self._poster_loaded)
        url_for = getattr(self.preview_loader, "url_for", None)
        if callable(url_for):
            self.remote_url = url_for(filename)
        requested_url = self.preview_loader.request(filename)
        if self.remote_url is None:
            self.remote_url = requested_url
        if self.remote_url is None:
            self._set_pixmap(None)

    def _poster_loaded(self, url, pixmap):
        if url == self.remote_url:
            self._set_pixmap(pixmap)

    def _set_pixmap(self, pixmap):
        self.preview.clear()
        if pixmap is None or pixmap.isNull():
            self.preview.setText("No preview")
            return
        self.preview.setPixmap(
            pixmap.scaled(
                MANAGE_POSTER_WIDTH,
                MANAGE_POSTER_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class ManagePostersDialog(QDialog):
    """Curate a draft poster selection without persisting it."""

    def __init__(
        self,
        parent,
        media_draft,
        *,
        discovery_manager=None,
        preview_loader=None,
        auto_discover=True,
    ):
        super().__init__(parent)
        self.media_draft = deepcopy(media_draft)
        self.result_payload = {"status": "cancelled"}
        self.discovery_manager = discovery_manager or PosterDiscoveryManager(self)
        self.preview_loader = preview_loader or TmdbPosterLoader(
            self,
            image_size=MANAGE_POSTER_PREVIEW_SIZE,
        )
        self.discovery_job_id = None
        self.cards = {}
        self._closing = False

        self._load_management_state()
        self.setWindowTitle("Manage Posters")
        self.setModal(True)
        self.setFixedSize(MANAGE_POSTERS_WIDTH, MANAGE_POSTERS_HEIGHT)
        self._build_ui()
        self._apply_styles()
        self._render_grid()

        self.discovery_manager.succeeded.connect(self._discovery_succeeded)
        self.discovery_manager.failed.connect(self._discovery_failed)
        self.discovery_manager.finished.connect(self._discovery_finished)
        if auto_discover:
            QTimer.singleShot(0, self.discover_posters)

    def _load_management_state(self):
        state = deepcopy(self.media_draft.get(POSTER_MANAGEMENT_KEY) or {})
        if state:
            self.candidates = state.get("candidates", [])
            for index, candidate in enumerate(self.candidates):
                candidate.setdefault("_candidate_order", index)
            self.selected_keys = set(state.get("selected_keys", []))
            self.default_key = state.get("default_key")
            self.checked_at = state.get("checked_at")
            return

        self.candidates = []
        self.selected_keys = set()
        self.default_key = None
        self.checked_at = None
        existing_media = self.media_draft.get("media_id") is not None
        is_episode = (
            (self.media_draft.get("metadata") or {}).get("media_type")
            == "episode"
        )
        has_direct_episode_poster = is_episode and any(
            poster.get("scope", "media") == "media"
            for poster in self.media_draft.get("posters", [])
        )
        for poster in self.media_draft.get("posters", []):
            candidate = deepcopy(poster)
            candidate["_management_origin"] = (
                "database" if existing_media else "draft"
            )
            candidate["_candidate_order"] = len(self.candidates)
            if candidate.get("source") == "user":
                local_path = MEDIA_POSTERS_DIR / str(
                    candidate.get("filename") or ""
                ).lstrip("/")
                if local_path.is_file():
                    candidate["_content_hash"] = _file_hash(local_path)
            key = _poster_key(candidate)
            if key is None or self._candidate_by_key(key) is not None:
                continue
            self.candidates.append(candidate)
            is_inherited_while_overridden = (
                has_direct_episode_poster
                and candidate.get("scope", "media") != "media"
            )
            if (
                not is_inherited_while_overridden
                and candidate.get("curation_status") not in {"failed", "discarded"}
            ):
                self.selected_keys.add(key)
            if candidate.get("is_default"):
                self.default_key = key

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        self.feedback_frame = QFrame(self)
        feedback_layout = QHBoxLayout(self.feedback_frame)
        feedback_layout.setContentsMargins(4, 0, 4, 0)
        feedback_layout.setSpacing(8)
        self.feedback_label = QLabel("", self.feedback_frame)
        self.retry_button = QPushButton("Retry", self.feedback_frame)
        self.retry_button.clicked.connect(self.discover_posters)
        feedback_layout.addWidget(self.feedback_label)
        feedback_layout.addWidget(self.retry_button)
        feedback_layout.addStretch()
        self.feedback_frame.hide()
        main_layout.addWidget(self.feedback_frame)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("managePostersScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.viewport().setObjectName("managePostersViewport")
        self.content = QWidget(self.scroll)
        self.content.setObjectName("managePostersContent")
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(10, 10, 10, 10)
        self.grid.setHorizontalSpacing(20)
        self.grid.setVerticalSpacing(10)
        self.grid.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        for column in range(MANAGE_POSTERS_COLUMNS):
            self.grid.setColumnMinimumWidth(column, MANAGE_POSTER_WIDTH)
        self.scroll.setWidget(self.content)
        main_layout.addWidget(self.scroll, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.cancel_button = QPushButton("Cancel", self)
        self.save_button = QPushButton("Save", self)
        for button in (self.cancel_button, self.save_button):
            button.setFixedSize(100, 32)
            footer.addWidget(button)
        footer.addStretch()
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.save)
        main_layout.addLayout(footer)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog { background-color: #f1f1f1; }
            QLabel, QCheckBox, QRadioButton {
                color: black;
                font-size: 12px;
                background: transparent;
            }
            QScrollArea#managePostersScroll,
            QWidget#managePostersViewport,
            QWidget#managePostersContent {
                background-color: white;
                border: none;
            }
            QLabel#managePosterPreview {
                background-color: #eeeeee;
                color: #707070;
            }
            QPushButton {
                background-color: white;
                color: black;
                border: 1px solid #bcbcbc;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f2f2f2; }
            QPushButton#importPosterButton {
                background-color: #eeeeee;
                border: none;
                border-radius: 0px;
            }
            QPushButton#importPosterButton:hover { background-color: #e3e3e3; }
        """)

    def _render_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.cards = {}

        self.import_container = QWidget(self.content)
        self.import_container.setFixedWidth(MANAGE_POSTER_WIDTH)
        import_layout = QVBoxLayout(self.import_container)
        import_layout.setContentsMargins(0, 0, 0, 0)
        import_layout.setSpacing(5)
        self.import_button = QPushButton("Import Poster", self.import_container)
        self.import_button.setObjectName("importPosterButton")
        self.import_button.setFixedSize(
            MANAGE_POSTER_WIDTH,
            MANAGE_POSTER_HEIGHT,
        )
        self.import_button.clicked.connect(self.import_poster)
        import_layout.addWidget(self.import_button)
        import_layout.addSpacing(22)
        self.grid.addWidget(
            self.import_container,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )

        for index, poster in enumerate(self._ordered_candidates(), start=1):
            key = _poster_key(poster)
            if key is None:
                continue
            card = PosterCard(poster, key, self.preview_loader, self.content)
            card.keep_changed.connect(self._keep_changed)
            card.default_clicked.connect(self._default_clicked)
            card.preview_requested.connect(self._open_poster_preview)
            card.set_state(
                key in self.selected_keys,
                key == self.default_key,
            )
            self.cards[key] = card
            row, column = divmod(index, MANAGE_POSTERS_COLUMNS)
            self.grid.addWidget(
                card,
                row,
                column,
                alignment=(
                    Qt.AlignmentFlag.AlignTop
                    | Qt.AlignmentFlag.AlignHCenter
                ),
            )

    def _open_poster_preview(self, poster):
        preview_dialog = PosterPreviewDialog(self, poster)
        preview_dialog.exec()

    def _ordered_candidates(self):
        def order(candidate):
            origin = candidate.get("_management_origin")
            if origin == "import":
                return (0, -int(candidate.get("_import_order", 0)), "")
            if origin in {"database", "draft"}:
                return (
                    1,
                    0 if _poster_key(candidate) == self.default_key else 1,
                    int(candidate.get("_candidate_order", 0)),
                )
            return (2, 0, int(candidate.get("_candidate_order", 0)))

        return sorted(self.candidates, key=order)

    def discover_posters(self):
        if self.discovery_job_id is not None:
            return
        self.feedback_label.setText("Loading TMDB posters…")
        self.retry_button.hide()
        self.feedback_frame.show()
        try:
            self.discovery_job_id = self.discovery_manager.start(
                build_tmdb_match_from_metadata(
                    self.media_draft.get("metadata") or {}
                )
            )
        except Exception as exc:
            self.discovery_job_id = None
            self._show_discovery_error(str(exc))

    def _discovery_succeeded(self, job_id, payload):
        if job_id != self.discovery_job_id or self._closing:
            return
        known = {
            _poster_key(candidate)
            for candidate in self.candidates
        }
        for raw_poster in payload.get("posters", []):
            poster = deepcopy(raw_poster)
            key = _poster_key(poster)
            if key is None or key in known:
                continue
            poster["_management_origin"] = "tmdb"
            poster["_candidate_order"] = len(self.candidates)
            self.candidates.append(poster)
            known.add(key)
        self.checked_at = payload.get("checked_at")
        self.feedback_frame.hide()
        self._render_grid()

    def _discovery_failed(self, job_id, payload):
        if job_id == self.discovery_job_id and not self._closing:
            self._show_discovery_error(
                payload.get("message") or "Could not load TMDB posters."
            )

    def _discovery_finished(self, job_id, _payload):
        if job_id == self.discovery_job_id:
            self.discovery_job_id = None

    def _show_discovery_error(self, message):
        self.feedback_label.setText(
            f"Could not load TMDB posters: {message}"
        )
        self.retry_button.show()
        self.feedback_frame.show()

    def import_poster(self):
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import Poster",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All Files (*)",
        )
        if not filename:
            return
        path = Path(filename)
        reader = QImageReader(str(path))
        image_format = bytes(reader.format()).decode("ascii", errors="ignore").lower()
        if (
            not path.is_file()
            or not reader.canRead()
            or not reader.size().isValid()
            or image_format in {"svg", "svgz"}
        ):
            QMessageBox.warning(self, "Import Poster", "Choose a valid raster image.")
            return

        content_hash = _file_hash(path)
        existing = next(
            (
                candidate
                for candidate in self.candidates
                if candidate.get("_content_hash") == content_hash
            ),
            None,
        )
        if existing is not None:
            key = _poster_key(existing)
            self.selected_keys.add(key)
            self._render_grid()
            self.scroll.ensureWidgetVisible(self.cards[key])
            return

        extension = path.suffix.lower() or f".{image_format or 'img'}"
        poster = {
            "scope": "media",
            "filename": f"user-{content_hash}{extension}",
            "source": "user",
            "curation_status": "selected",
            "is_default": False,
            "series_tmdb_id": None,
            "season_num": None,
            "_management_origin": "import",
            "_import_path": str(path),
            "_content_hash": content_hash,
            "_import_order": max(
                [candidate.get("_import_order", 0) for candidate in self.candidates]
                + [0]
            ) + 1,
        }
        self.candidates.append(poster)
        self.selected_keys.add(_poster_key(poster))
        self._render_grid()

    def _keep_changed(self, key, checked):
        if checked:
            self.selected_keys.add(key)
        else:
            self.selected_keys.discard(key)
            if self.default_key == key:
                self.default_key = None
        self._sync_card_states()

    def _default_clicked(self, key):
        if key not in self.selected_keys:
            return
        self.default_key = None if self.default_key == key else key
        self._sync_card_states()

    def _sync_card_states(self):
        for key, card in self.cards.items():
            card.set_state(key in self.selected_keys, key == self.default_key)

    def save(self):
        selected_posters = []
        for candidate in self._ordered_candidates():
            key = _poster_key(candidate)
            if key not in self.selected_keys:
                continue
            poster = deepcopy(candidate)
            poster["curation_status"] = "selected"
            poster["is_default"] = key == self.default_key
            if (
                (self.media_draft.get("metadata") or {}).get("media_type")
                == "episode"
            ):
                poster["scope"] = "media"
                poster["series_tmdb_id"] = None
                poster["season_num"] = None
            selected_posters.append(poster)

        state = {
            "candidates": deepcopy(self.candidates),
            "selected_keys": list(self.selected_keys),
            "default_key": self.default_key,
            "checked_at": self.checked_at,
        }
        self.result_payload = {
            "status": "saved",
            "posters": selected_posters,
            "management_state": state,
        }
        self._closing = True
        if self.discovery_job_id is not None:
            self.discovery_manager.cancel(self.discovery_job_id)
            self.discovery_job_id = None
        self.accept()

    def reject(self):
        self._closing = True
        if self.discovery_job_id is not None:
            self.discovery_manager.cancel(self.discovery_job_id)
            self.discovery_job_id = None
        super().reject()

    def _candidate_by_key(self, key):
        return next(
            (
                candidate
                for candidate in self.candidates
                if _poster_key(candidate) == key
            ),
            None,
        )


def _poster_key(poster):
    filename = str(poster.get("filename") or "").lstrip("/")
    return f"poster:{filename}" if filename else None


def _poster_local_path(poster):
    import_path = poster.get("_import_path")
    if import_path:
        candidate = Path(import_path)
        if candidate.is_file():
            return candidate

    filename = str(poster.get("filename") or "").lstrip("/")
    candidate = MEDIA_POSTERS_DIR / filename
    return candidate if candidate.is_file() else None


def _file_hash(path):
    digest = sha256()
    with Path(path).open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "LARGE_POSTER_PREVIEW_SIZE",
    "MANAGE_POSTERS_COLUMNS",
    "MANAGE_POSTERS_HEIGHT",
    "MANAGE_POSTERS_WIDTH",
    "ManagePostersDialog",
    "PosterPreviewDialog",
    "POSTER_MANAGEMENT_KEY",
    "PosterDiscoveryManager",
]
