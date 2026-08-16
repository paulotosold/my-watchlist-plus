"""Dialog for choosing between TMDB movie and series search results."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.paths import MEDIA_POSTERS_DIR
from app.tmdb import build_tmdb_image_url
from app.ui.clickable_entry_label import ClickableEntryLabel
from app.ui.top_bar import INPUT_BOX_STYLE


POSTER_DIR = MEDIA_POSTERS_DIR
POSTER_WIDTH = 100
POSTER_HEIGHT = 150
MATCH_SELECTION_WIDTH = 900
MATCH_SELECTION_HEIGHT = 680
MATCH_SELECTION_MINIMUM_HEIGHT = 600
MATCH_SELECTION_INPUT_HEIGHT = 32
MATCH_SELECTION_BUTTON_WIDTH = 100
MATCH_SELECTION_BUTTON_MINIMUM_HEIGHT = 32
TMDB_MATCH_POSTER_SIZE = "w92"
TMDB_POSTER_TIMEOUT_MS = 8_000

MATCH_SELECTION_STYLE = """
QDialog {
    background-color: #f1f1f1;
}

QLabel {
    color: black;
    background: transparent;
}

QScrollArea#matchCandidateScroll,
QWidget#matchCandidateScrollViewport,
QWidget#matchCandidateContent,
QWidget#matchCandidateRow {
    background-color: white;
    border: none;
}

QLabel#matchCandidatePoster {
    background-color: #e3e3e3;
    color: #707070;
}

QLabel#matchEmptyColumn {
    color: #707070;
    padding: 12px;
}

QPushButton {
    background-color: white;
    color: black;
    border: 1px solid #bcbcbc;
    border-radius: 6px;
    padding: 6px 12px;
}

QPushButton:hover {
    background-color: #f2f2f2;
}
"""


class TmdbPosterLoader(QObject):
    """Load and cache small TMDB posters without blocking the dialog."""

    poster_loaded = Signal(str, object)

    def __init__(self, parent=None, network_manager=None, image_size=None):
        super().__init__(parent)

        self.network_manager = (
            network_manager or QNetworkAccessManager(self)
        )
        self._cache = {}
        self._pending = {}
        self._reply_urls = {}
        self.image_size = image_size or TMDB_MATCH_POSTER_SIZE

    def url_for(self, poster_path):
        return _tmdb_poster_url(poster_path, size=self.image_size)

    def request(self, poster_path):
        url = self.url_for(poster_path)

        if url is None:
            return None

        if url in self._cache:
            self.poster_loaded.emit(url, self._cache[url])
            return url

        if url in self._pending:
            return url

        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(TMDB_POSTER_TIMEOUT_MS)
        reply = self.network_manager.get(request)
        self._pending[url] = reply
        self._reply_urls[reply] = url
        reply.finished.connect(self._on_reply_finished)
        return url

    def _on_reply_finished(self):
        reply = self.sender()
        url = self._reply_urls.pop(reply, None)

        if url is None:
            if reply is not None:
                reply.deleteLater()
            return

        self._pending.pop(url, None)
        pixmap = None

        if reply.error() == QNetworkReply.NetworkError.NoError:
            loaded_pixmap = QPixmap()

            if loaded_pixmap.loadFromData(bytes(reply.readAll())):
                pixmap = loaded_pixmap

        self._cache[url] = pixmap
        reply.deleteLater()
        self.poster_loaded.emit(url, pixmap)


class MatchCandidateWidget(QWidget):
    """Lightweight candidate row; only its title triggers selection."""

    def __init__(
        self,
        candidate,
        parent=None,
        callback=None,
        poster_loader=None,
    ):
        super().__init__(parent)

        self.candidate = candidate
        self.poster_loader = poster_loader
        self._remote_poster_url = None
        self.setObjectName("matchCandidateRow")
        self.setMinimumHeight(POSTER_HEIGHT + 16)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.poster_label = QLabel(self)
        self.poster_label.setObjectName("matchCandidatePoster")
        self.poster_label.setFixedSize(POSTER_WIDTH, POSTER_HEIGHT)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._render_poster()

        details = QWidget(self)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(0)

        self.title_label = ClickableEntryLabel(
            candidate.get("title") or "Untitled",
            details,
            callback,
        )
        self.title_label.setObjectName("matchCandidateTitle")
        self.title_label.setToolTip(candidate.get("title") or "Untitled")
        self.title_label.setFixedHeight(28)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        title_font = self.title_label.font()
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.year_label = QLabel(_candidate_year(candidate), details)
        self.year_label.setObjectName("matchCandidateYear")

        details_layout.addWidget(self.title_label)
        details_layout.addWidget(self.year_label)
        details_layout.addStretch()

        layout.addWidget(
            self.poster_label,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        layout.addWidget(details, stretch=1)

    def _render_poster(self):
        pixmap = _load_local_poster(self.candidate)

        if pixmap is not None:
            self._set_poster_pixmap(pixmap)
            return

        poster_path = _remote_poster_path(self.candidate)
        remote_url = _tmdb_poster_url(poster_path)

        if remote_url is None or self.poster_loader is None:
            self._set_poster_pixmap(None)
            return

        self._remote_poster_url = remote_url
        self.poster_loader.poster_loaded.connect(
            self._on_remote_poster_loaded
        )
        self.poster_label.setText("Loading…")
        self.poster_loader.request(poster_path)

    def _on_remote_poster_loaded(self, url, pixmap):
        if url != self._remote_poster_url:
            return

        self._set_poster_pixmap(pixmap)

    def _set_poster_pixmap(self, pixmap):
        self.poster_label.clear()

        if pixmap is None or pixmap.isNull():
            self.poster_label.setText("No poster")
            return

        self.poster_label.setText("")
        self.poster_label.setPixmap(
            pixmap.scaled(
                POSTER_WIDTH,
                POSTER_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class MatchSelectionDialog(QDialog):
    """Present TMDB search candidates and optionally restart Find Media.

    The accepted ``result_payload`` uses ``selected`` or ``restart``.
    Rejection always leaves it as ``cancelled``.
    """

    def __init__(
        self,
        parent,
        query,
        candidates,
        poster_loader=None,
    ):
        super().__init__(parent)

        self.current_query = (query or "").strip()
        self.candidates = []
        self.result_payload = {"status": "cancelled"}
        self.candidate_widgets = {"movie": [], "series": []}
        self.poster_loader = poster_loader or TmdbPosterLoader(self)

        self.setWindowTitle("Match Selection")
        self.setModal(True)
        self.setMinimumSize(
            MATCH_SELECTION_WIDTH,
            MATCH_SELECTION_MINIMUM_HEIGHT,
        )
        self.resize(MATCH_SELECTION_WIDTH, MATCH_SELECTION_HEIGHT)

        self._build_ui()
        self.setStyleSheet(MATCH_SELECTION_STYLE)
        self.set_candidates(candidates)

    @property
    def movie_candidate_widgets(self):
        return self.candidate_widgets["movie"]

    @property
    def series_candidate_widgets(self):
        return self.candidate_widgets["series"]

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(48, 28, 48, 28)
        main_layout.setSpacing(18)

        query_layout = QHBoxLayout()
        query_layout.setContentsMargins(0, 0, 0, 0)
        query_layout.setSpacing(12)

        self.find_media_label = QLabel("Find Media:", self)
        self.find_media_input = QLineEdit(self)
        self.find_media_input.setObjectName("matchQueryInput")
        self.find_media_input.setFixedHeight(MATCH_SELECTION_INPUT_HEIGHT)
        self.find_media_input.setClearButtonEnabled(True)
        self.find_media_input.setText(self.current_query)
        self.find_media_input.setStyleSheet(INPUT_BOX_STYLE)
        self.find_media_input.returnPressed.connect(self.refine_search)

        query_layout.addWidget(self.find_media_label)
        query_layout.addWidget(self.find_media_input, stretch=1)

        self.instruction_label = QLabel(
            (
                "The current query returned multiple results. "
                "Choose one below, or refine the search."
            ),
            self,
        )
        self.instruction_label.setObjectName("matchInstruction")

        columns_layout = QHBoxLayout()
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(40)

        movie_column, self.movie_scroll, self.movie_candidates_layout = (
            self._build_candidate_column("Movies")
        )
        series_column, self.series_scroll, self.series_candidates_layout = (
            self._build_candidate_column("Series")
        )

        columns_layout.addLayout(movie_column, stretch=1)
        columns_layout.addLayout(series_column, stretch=1)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setFixedWidth(MATCH_SELECTION_BUTTON_WIDTH)
        self.cancel_button.setMinimumHeight(
            MATCH_SELECTION_BUTTON_MINIMUM_HEIGHT
        )
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addStretch()

        main_layout.addLayout(query_layout)
        main_layout.addWidget(self.instruction_label)
        main_layout.addLayout(columns_layout, stretch=1)
        main_layout.addLayout(footer_layout)

    def _build_candidate_column(self, title):
        column_layout = QVBoxLayout()
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        title_label = QLabel(title, self)
        title_label.setObjectName("matchColumnTitle")

        scroll = QScrollArea(self)
        scroll.setObjectName("matchCandidateScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setObjectName("matchCandidateScrollViewport")

        content = QWidget(scroll)
        content.setObjectName("matchCandidateContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        scroll.setWidget(content)

        column_layout.addWidget(title_label)
        column_layout.addWidget(scroll, stretch=1)
        return column_layout, scroll, content_layout

    def set_candidates(self, candidates):
        """Replace both columns while retaining the current dialog instance."""
        self.candidates = [
            candidate
            for candidate in (candidates or [])
            if candidate.get("media_type") in self.candidate_widgets
        ]

        for media_type, layout in (
            ("movie", self.movie_candidates_layout),
            ("series", self.series_candidates_layout),
        ):
            _clear_layout(layout)
            self.candidate_widgets[media_type] = []

            matching_candidates = [
                candidate
                for candidate in self.candidates
                if candidate.get("media_type") == media_type
            ]

            for candidate in matching_candidates:
                candidate_widget = MatchCandidateWidget(
                    candidate,
                    parent=layout.parentWidget(),
                    callback=lambda candidate=candidate: self._select_candidate(
                        candidate
                    ),
                    poster_loader=self.poster_loader,
                )
                self.candidate_widgets[media_type].append(candidate_widget)
                layout.addWidget(candidate_widget)

            if not matching_candidates:
                empty_label = QLabel(
                    f"No {media_type} results.",
                    layout.parentWidget(),
                )
                empty_label.setObjectName("matchEmptyColumn")
                layout.addWidget(empty_label)

            layout.addStretch()

    def refine_search(self):
        query = self.find_media_input.text().strip()

        if not query:
            QMessageBox.warning(
                self,
                "Find Media",
                "Enter an IMDb ID, title, or media description first.",
            )
            return

        self.result_payload = {
            "status": "restart",
            "query": query,
        }
        self.accept()

    def _select_candidate(self, candidate):
        self.result_payload = {
            "status": "selected",
            "candidate": candidate,
        }
        self.accept()


def _candidate_year(candidate):
    date_value = candidate.get("release_date") or candidate.get("year")

    if date_value is None:
        return ""

    value = str(date_value).strip()
    return value[:4] if len(value) >= 4 and value[:4].isdigit() else value


def _load_local_poster(candidate):
    if candidate.get("source") != "db":
        return None

    filename = candidate.get("poster_path") or candidate.get("filename")
    poster = candidate.get("poster")

    if not filename and isinstance(poster, dict):
        filename = poster.get("filename")

    if not filename:
        return None

    path = Path(str(filename))

    if not path.is_absolute():
        path = POSTER_DIR / str(filename).lstrip("/")

    if not path.is_file():
        return None

    pixmap = QPixmap(str(path))
    return pixmap if not pixmap.isNull() else None


def _remote_poster_path(candidate):
    if candidate.get("source") == "tmdb":
        return candidate.get("poster_path")

    return candidate.get("remote_poster_path")


def _tmdb_poster_url(poster_path, size=TMDB_MATCH_POSTER_SIZE):
    return build_tmdb_image_url(
        poster_path,
        size=size,
    )


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()

        if widget is not None:
            widget.deleteLater()
