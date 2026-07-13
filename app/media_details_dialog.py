from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import requests

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import app.draft_saver as draft_saver
import app.media_repository as media_repo
import app.tmdb_fetcher as tmdb_fetcher
from app.media_details_state import (
    apply_inserted_ids_to_draft,
    merge_metadata_refresh,
)
from app.metadata_refresh import get_metadata_refresh_manager
from app.media_details_formatters import (
    WATCH_PROVIDER_GROUPS,
    build_metadata_display_rows,
    build_tmdb_match_from_metadata,
    build_watch_history_display_entries,
    format_episode_ranges,
    format_watch_history_entry,
    format_watch_provider_checked_at,
    get_poster_curation_status,
    group_watch_providers,
)
from app.media_lookup import resolve_media_draft_from_query
from app.watch_history_editor import (
    WATCH_ENTRY_DATE_INPUT_WIDTH,
    WATCH_ENTRY_EPISODE_BUTTON_BORDER_RADIUS,
    WATCH_ENTRY_EPISODE_BUTTON_FONT_SIZE,
    WATCH_ENTRY_EPISODE_BUTTON_HEIGHT,
    WATCH_ENTRY_EPISODE_BUTTON_SPACING,
    WATCH_ENTRY_EPISODE_BUTTON_SELECTED_COLOR,
    WATCH_ENTRY_EPISODE_BUTTON_WATCHED_COLOR,
    WATCH_ENTRY_EPISODE_BUTTON_WIDTH,
    WATCH_ENTRY_EPISODES_TO_BUTTONS_SPACING,
    WATCH_ENTRY_HEADER_TO_BUTTONS_SPACING,
    WATCH_ENTRY_HEADER_TO_EPISODES_SPACING,
    WATCH_ENTRY_SEASON_ROW_SPACING,
    apply_watch_entry_result,
    episode_key,
    get_series_episodes,
    is_episode_available,
    make_draft_id,
    validate_watch_dates,
    watched_episode_keys,
)
from app.watch_states import VALID_WATCH_STATES_BY_MEDIA_TYPE
from db.connection import get_connection


DETAIL_ICON_DIR = Path("app/assets")
POSTER_DIR = Path("data/media_posters")
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
TMDB_POSTER_PREVIEW_SIZE = "w185"
POSTER_PREVIEW_HEIGHT = 232
# Tweak this value to fine-tune vertical spacing in open dropdown menus.
COMBO_POPUP_ITEM_HEIGHT = 28
DETAIL_HEADER_ICON_TEXT_SPACING = 1
DETAIL_ACTION_LINE_ICON_TEXT_SPACING = 1
DETAIL_ICON_BUTTON_SIZE = 20
DETAIL_ICON_SIZE = 18
DETAIL_BUTTON_WIDTH = 100
WATCH_ENTRY_BACKGROUND_COLOR = "#f1f1f1"
WATCH_ENTRY_DIALOG_DEFAULT_WIDTH = 960
WATCH_ENTRY_DIALOG_MAX_HEIGHT = 750
WATCH_ENTRY_EPISODE_SELECTOR_MAX_HEIGHT = 520
WATCH_ENTRY_DATE_GROUP_SPACING = 2
WATCH_ENTRY_SEASON_LABEL_WIDTH = 60
WATCH_ENTRY_SEASON_LABEL_BUTTON_SPACING = 20

WATCH_STATE_OPTION_ORDER = (
    "to_watch",
    "watched",
    "not_interested",
    "dropped",
)
WATCH_STATE_LABELS = {
    "to_watch": "To Watch",
    "watched": "Watched",
    "not_interested": "Not Interested",
    "dropped": "Dropped",
}
NO_WATCH_STATE_LABELS = {
    "movie": "Not in watchlist",
    "series": "Not in watchlist",
    "episode": "No individual status",
}
STATUS_OPTIONS_BY_MEDIA_TYPE = {
    media_type: (
        (None, NO_WATCH_STATE_LABELS[media_type]),
        *(
            (watch_state, WATCH_STATE_LABELS[watch_state])
            for watch_state in WATCH_STATE_OPTION_ORDER
            if watch_state in allowed_states
        ),
    )
    for media_type, allowed_states in VALID_WATCH_STATES_BY_MEDIA_TYPE.items()
}

IMPRESSION_OPTIONS = (
    (None, "None"),
    ("very_good", "👍👍 Very good"),
    ("good", "👍 Good"),
    ("meh", "😐 Meh"),
    ("not_for_me", "Not for me"),
    ("regret_watching", "😡 Waste of time"),
)

COLLECTION_PICK_OPTIONS = (
    (None, "None"),
    (True, "Yes!"),
    (False, "No"),
)


def open_media_details_dialog(parent, media_draft, input_query=None):
    dialog = MediaDetailsDialog(
        parent=parent,
        media_draft=media_draft,
        input_query=input_query,
    )

    if dialog.exec() == QDialog.Accepted:
        return dialog.result_payload

    return {"status": "cancelled"}


class DetailBlock(QFrame):
    def __init__(self, title, icon_name=None, parent=None):
        super().__init__(parent)

        self.setObjectName("detailBlock")
        self.action_button = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 10, 12, 12)
        self.main_layout.setSpacing(5)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(DETAIL_HEADER_ICON_TEXT_SPACING)

        if icon_name:
            self.action_button = make_icon_button(icon_name, self)
            header_layout.addWidget(self.action_button)

        title_label = QLabel(title, self)
        title_label.setObjectName("blockTitle")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(3)

        self.main_layout.addLayout(header_layout)
        self.main_layout.addLayout(self.body_layout, stretch=1)


class DownwardComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._user_activation_previous_data = None

    def showPopup(self):
        self._user_activation_previous_data = self.currentData()
        super().showPopup()

        popup = self.view().window()

        if popup is not None:
            popup.move(self.mapToGlobal(QPoint(0, self.height())))

    def keyPressEvent(self, event):
        self._user_activation_previous_data = self.currentData()
        super().keyPressEvent(event)

    def reset_user_activation_baseline(self):
        self._user_activation_previous_data = self.currentData()

    def take_user_activation_previous_data(self):
        previous_data = self._user_activation_previous_data
        self._user_activation_previous_data = self.currentData()
        return previous_data


class ComboPopupView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_index = QModelIndex()
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def mouseMoveEvent(self, event):
        self.hovered_index = self.indexAt(event.position().toPoint())
        self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_index = QModelIndex()
        self.viewport().update()
        super().leaveEvent(event)


class ComboPopupItemDelegate(QStyledItemDelegate):
    def __init__(self, combo, parent=None):
        super().__init__(parent)
        self.combo = combo

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(COMBO_POPUP_ITEM_HEIGHT)
        return size

    def paint(self, painter, option, index):
        view = option.widget
        hovered_index = getattr(view, "hovered_index", QModelIndex())
        is_hovered = (
            hovered_index == index
            or bool(option.state & QStyle.StateFlag.State_MouseOver)
            or bool(option.state & QStyle.StateFlag.State_Selected)
        )
        is_current = index.row() == self.combo.currentIndex()

        painter.save()
        painter.fillRect(
            option.rect,
            QColor("#f2f2f2") if is_hovered else QColor("white"),
        )
        painter.setPen(QColor("black"))
        painter.setFont(option.font)

        if is_current:
            painter.drawText(
                option.rect.adjusted(10, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "✓",
            )

        painter.drawText(
            option.rect.adjusted(34, 0, -12, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            str(index.data(Qt.ItemDataRole.DisplayRole)),
        )
        painter.restore()


class WatchEntryDetailsDialog(QDialog):
    def __init__(self, parent, media_draft, entry=None):
        super().__init__(parent)

        self.media_draft = deepcopy(media_draft)
        self.entry = deepcopy(entry) if entry is not None else None
        self.result_payload = {"action": "cancel"}
        self.episode_buttons = {}
        self.initial_signature = None

        self.setWindowTitle("Watch Entry Details")
        self.setMinimumWidth(WATCH_ENTRY_DIALOG_DEFAULT_WIDTH)
        self.setMaximumHeight(WATCH_ENTRY_DIALOG_MAX_HEIGHT)
        self._apply_parent_styles(parent)
        self._build_ui()
        self.resize(
            WATCH_ENTRY_DIALOG_DEFAULT_WIDTH,
            min(self.sizeHint().height(), WATCH_ENTRY_DIALOG_MAX_HEIGHT),
        )
        self._populate_initial_values()
        self.initial_signature = self._current_signature()
        self._refresh_state()

    def _apply_parent_styles(self, parent):
        parent_style = parent.styleSheet() if parent is not None else ""
        self.setStyleSheet(parent_style + f"""
            QLabel#errorLabel {{
                color: #b00020;
            }}

            QScrollArea#episodeSelectorScroll,
            QScrollArea#episodeSelectorScroll > QWidget,
            QScrollArea#episodeSelectorScroll > QWidget > QWidget,
            QWidget#episodeSelectorContent,
            QFrame#dialogButtonBar {{
                background-color: {WATCH_ENTRY_BACKGROUND_COLOR};
                border: none;
            }}

            QPushButton#episodeButton {{
                min-width: {WATCH_ENTRY_EPISODE_BUTTON_WIDTH}px;
                max-width: {WATCH_ENTRY_EPISODE_BUTTON_WIDTH}px;
                min-height: {WATCH_ENTRY_EPISODE_BUTTON_HEIGHT}px;
                max-height: {WATCH_ENTRY_EPISODE_BUTTON_HEIGHT}px;
                padding: 0px;
                border: 1px solid #bcbcbc;
                border-radius: {WATCH_ENTRY_EPISODE_BUTTON_BORDER_RADIUS}px;
                background-color: white;
                color: black;
                font-size: {WATCH_ENTRY_EPISODE_BUTTON_FONT_SIZE}px;
            }}

            QPushButton#episodeButton[watchState="watched"] {{
                background-color: {WATCH_ENTRY_EPISODE_BUTTON_WATCHED_COLOR};
            }}

            QPushButton#episodeButton[watchState="selected"] {{
                background-color: {WATCH_ENTRY_EPISODE_BUTTON_SELECTED_COLOR};
            }}
        """)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(0)

        date_layout = QHBoxLayout()
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(16)

        self.date_earliest_input = self._make_date_input()
        self.date_latest_input = self._make_date_input()
        self.preview_label = QLabel(self)
        self.preview_label.setWordWrap(False)

        date_layout.addWidget(QLabel("Earliest Date:", self))
        date_layout.addWidget(self.date_earliest_input)
        date_layout.addSpacing(WATCH_ENTRY_DATE_GROUP_SPACING)
        date_layout.addWidget(QLabel("Latest Date:", self))
        date_layout.addWidget(self.date_latest_input)
        date_layout.addSpacing(WATCH_ENTRY_DATE_GROUP_SPACING)
        date_layout.addWidget(self.preview_label, stretch=1)
        main_layout.addLayout(date_layout)

        if self._is_series():
            main_layout.addSpacing(WATCH_ENTRY_HEADER_TO_EPISODES_SPACING)
            main_layout.addWidget(self._build_episode_selector())
            main_layout.addSpacing(WATCH_ENTRY_EPISODES_TO_BUTTONS_SPACING)
        else:
            main_layout.addSpacing(WATCH_ENTRY_HEADER_TO_BUTTONS_SPACING)

        self.error_label = QLabel(self)
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        main_layout.addWidget(self.error_label)

        main_layout.addWidget(self._build_button_bar())

    def _make_date_input(self):
        input_widget = QLineEdit(self)
        input_widget.setFixedHeight(32)
        input_widget.setFixedWidth(WATCH_ENTRY_DATE_INPUT_WIDTH)
        input_widget.textChanged.connect(self._refresh_state)
        return input_widget

    def _build_episode_selector(self):
        scroll = QScrollArea(self)
        scroll.setObjectName("episodeSelectorScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(WATCH_ENTRY_EPISODE_SELECTOR_MAX_HEIGHT)

        content = QWidget(scroll)
        content.setObjectName("episodeSelectorContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(WATCH_ENTRY_SEASON_ROW_SPACING)

        episodes_by_season = {}

        for episode in self._selectable_episodes():
            episodes_by_season.setdefault(episode.get("season_num"), []).append(episode)

        if not episodes_by_season:
            content_layout.addWidget(QLabel("No episodes available.", self))
        else:
            for season_num in sorted(episodes_by_season):
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(WATCH_ENTRY_SEASON_LABEL_BUTTON_SPACING)

                season_label = QLabel(f"Season {season_num}:", self)
                season_label.setFixedWidth(WATCH_ENTRY_SEASON_LABEL_WIDTH)
                row_layout.addWidget(season_label)

                episode_buttons_layout = QHBoxLayout()
                episode_buttons_layout.setContentsMargins(0, 0, 0, 0)
                episode_buttons_layout.setSpacing(WATCH_ENTRY_EPISODE_BUTTON_SPACING)

                for episode in sorted(
                    episodes_by_season[season_num],
                    key=lambda item: item.get("episode_num") or 0,
                ):
                    key = episode_key(episode)
                    button = QPushButton(f"E{episode.get('episode_num')}", self)
                    button.setObjectName("episodeButton")
                    button.setCheckable(True)
                    button.setFixedSize(
                        WATCH_ENTRY_EPISODE_BUTTON_WIDTH,
                        WATCH_ENTRY_EPISODE_BUTTON_HEIGHT,
                    )
                    button.setChecked(self._entry_selects_episode(episode))
                    button.setToolTip(self._episode_tooltip(episode))

                    if not is_episode_available(episode):
                        button.setEnabled(False)

                    button.clicked.connect(
                        lambda checked=False, key=key: self._episode_toggled(key)
                    )
                    self.episode_buttons[key] = (button, episode)
                    episode_buttons_layout.addWidget(button)

                row_layout.addLayout(episode_buttons_layout)
                row_layout.addStretch()
                content_layout.addLayout(row_layout)

        content_layout.addStretch()
        scroll.setWidget(content)
        scroll.setFixedHeight(
            min(
                content.sizeHint().height(),
                WATCH_ENTRY_EPISODE_SELECTOR_MAX_HEIGHT,
            )
        )
        return scroll

    def _build_button_bar(self):
        bar = QFrame(self)
        bar.setObjectName("dialogButtonBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)
        layout.addStretch()

        self.delete_entry_button = QPushButton("DELETE", bar)
        self.delete_entry_button.setObjectName("deleteButton")
        self.cancel_entry_button = QPushButton("Cancel", bar)
        self.save_entry_button = QPushButton("Save", bar)

        for button in (
            self.delete_entry_button,
            self.cancel_entry_button,
            self.save_entry_button,
        ):
            button.setMinimumHeight(32)
            button.setFixedWidth(DETAIL_BUTTON_WIDTH)
            layout.addWidget(button)

        layout.addStretch()

        self.delete_entry_button.clicked.connect(self._delete_entry)
        self.cancel_entry_button.clicked.connect(self.reject)
        self.save_entry_button.clicked.connect(self._save_entry)

        return bar

    def _populate_initial_values(self):
        self.date_earliest_input.setText(
            (self.entry or {}).get("date_earliest") or ""
        )
        self.date_latest_input.setText(
            (self.entry or {}).get("date_latest") or ""
        )

    def _selectable_episodes(self):
        catalog_episodes = get_series_episodes(self.media_draft)
        catalog_by_episode_id = {
            episode.get("episode_id"): episode
            for episode in catalog_episodes
            if episode.get("episode_id") is not None
        }
        catalog_by_tmdb_id = {
            episode.get("tmdb_id"): episode
            for episode in catalog_episodes
            if episode.get("tmdb_id") is not None
        }
        catalog_by_key = {
            episode_key(episode): episode
            for episode in catalog_episodes
            if episode_key(episode) != (None, None)
        }
        selected_episodes = (self.entry or {}).get("episodes", [])
        episodes_by_key = {}

        for episode in catalog_episodes:
            key = episode_key(episode)

            if key == (None, None):
                continue

            if is_episode_available(episode) or self._entry_selects_episode(episode):
                episodes_by_key[key] = deepcopy(episode)

        for selected_episode in selected_episodes:
            episode = None
            episode_id = selected_episode.get("episode_id")
            tmdb_id = selected_episode.get("tmdb_id")

            if episode_id is not None:
                episode = catalog_by_episode_id.get(episode_id)

            if episode is None and tmdb_id is not None:
                episode = catalog_by_tmdb_id.get(tmdb_id)

            if episode is None:
                episode = catalog_by_key.get(episode_key(selected_episode))

            episode = episode or selected_episode
            key = episode_key(episode)

            if key != (None, None):
                episodes_by_key[key] = deepcopy(episode)

        return sorted(
            episodes_by_key.values(),
            key=lambda item: (
                item.get("season_num") or 0,
                item.get("episode_num") or 0,
            ),
        )

    def _entry_selects_episode(self, episode):
        episode_id = episode.get("episode_id")
        tmdb_id = episode.get("tmdb_id")
        key = episode_key(episode)

        for selected_episode in (self.entry or {}).get("episodes", []):
            selected_episode_id = selected_episode.get("episode_id")
            selected_tmdb_id = selected_episode.get("tmdb_id")

            if (
                episode_id is not None
                and selected_episode_id is not None
                and episode_id == selected_episode_id
            ):
                return True

            if (
                tmdb_id is not None
                and selected_tmdb_id is not None
                and tmdb_id == selected_tmdb_id
            ):
                return True

            if key != (None, None) and key == episode_key(selected_episode):
                return True

        return False

    def _episode_tooltip(self, episode):
        season_num, episode_num = episode_key(episode)
        title = (
            episode.get("title")
            or episode.get("episode_title")
            or f"Season {season_num}, Episode {episode_num}"
        )

        if is_episode_available(episode):
            return title

        return (
            f"{title}\n"
            "Unavailable (not released yet or release date unknown)."
        )

    def _episode_toggled(self, key):
        self._refresh_episode_button(key)
        self._refresh_state()

    def _refresh_state(self):
        validation = self._validated_dates()
        self.error_label.setText(validation["error"] or "")
        self.error_label.setVisible(bool(validation["error"]))
        self.preview_label.setText(f"Preview: {self._preview_text(validation)}")

        for key in self.episode_buttons:
            self._refresh_episode_button(key)

        is_changed = self._current_signature() != self.initial_signature
        can_save = self.entry is None or is_changed
        self.save_entry_button.setEnabled(validation["is_valid"] and can_save)
        self.delete_entry_button.setEnabled(self.entry is not None)

    def _refresh_episode_button(self, key):
        button, _episode = self.episode_buttons[key]
        watched_keys = watched_episode_keys(self.media_draft, self.entry)
        watch_state = "selected" if button.isChecked() else ""

        if not watch_state and key in watched_keys:
            watch_state = "watched"

        button.setProperty("watchState", watch_state)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _validated_dates(self):
        return validate_watch_dates(
            self.date_earliest_input.text(),
            self.date_latest_input.text(),
        )

    def _preview_text(self, validation=None):
        validation = validation or self._validated_dates()

        if not validation["is_valid"]:
            return "Invalid date"

        event = {
            "date_earliest": validation["date_earliest"],
            "date_latest": validation["date_latest"],
        }
        release_date = self._watch_history_release_date()
        preview = format_watch_history_entry(event, release_date=release_date)

        if not self._is_series():
            return preview

        selected_episodes = self._selected_episodes()

        if selected_episodes:
            return f"{preview} · {format_episode_ranges(selected_episodes)}"

        return f"{preview} · no episode info"

    def _current_signature(self):
        validation = self._validated_dates()

        if not validation["is_valid"]:
            return None

        return (
            validation["date_earliest"],
            validation["date_latest"],
            tuple(
                sorted(
                    episode_key(episode)
                    for episode in self._selected_episodes()
                )
            ),
        )

    def _selected_episodes(self):
        return [
            deepcopy(episode)
            for button, episode in self.episode_buttons.values()
            if button.isChecked()
        ]

    def _watch_history_release_date(self):
        metadata = self.media_draft.get("metadata") or {}

        if metadata.get("media_type") == "series":
            series_view = self.media_draft.get("series_view") or {}
            summary = series_view.get("summary") or {}
            return summary.get("first_air_date") or metadata.get("release_date")

        return metadata.get("release_date")

    def _is_series(self):
        return (self.media_draft.get("metadata") or {}).get("media_type") == "series"

    def _save_entry(self):
        validation = self._validated_dates()

        if not validation["is_valid"]:
            return

        self.result_payload = {
            "action": "save",
            "date_earliest": validation["date_earliest"],
            "date_latest": validation["date_latest"],
            "selected_episodes": self._selected_episodes(),
        }
        self.accept()

    def _delete_entry(self):
        if self.entry is None:
            return

        self.result_payload = {"action": "delete"}
        self.accept()


class MediaDetailsDialog(QDialog):
    def __init__(
        self,
        parent,
        media_draft,
        input_query=None,
        metadata_refresh_manager=None,
    ):
        super().__init__(parent)

        self.media_draft = deepcopy(media_draft)
        self.result_payload = {"status": "cancelled"}
        self.all_lists = []
        self.list_checkboxes = []
        self._is_dirty = False
        self._is_populating = False
        self._baseline_media_draft = deepcopy(media_draft)
        self._metadata_refresh_job_id = None
        self._metadata_refresh_in_progress = False
        self._is_closing = False
        self._watch_entry_dialog_active = False
        self._status_change_generation = 0
        self._scheduled_watch_entry_generation = None
        self.metadata_refresh_manager = (
            metadata_refresh_manager or get_metadata_refresh_manager()
        )
        self.metadata_refresh_manager.progress.connect(
            self._on_metadata_refresh_progress
        )
        self.metadata_refresh_manager.succeeded.connect(
            self._on_metadata_refresh_succeeded
        )
        self.metadata_refresh_manager.failed.connect(
            self._on_metadata_refresh_failed
        )
        self.metadata_refresh_manager.cancelled.connect(
            self._on_metadata_refresh_cancelled
        )
        self.metadata_refresh_manager.finished.connect(
            self._on_metadata_refresh_finished
        )

        self.setWindowTitle("Media Details")
        self.setFixedSize(1320, 850)

        self._load_all_lists()
        self._build_ui(input_query)
        self._apply_styles()
        self.set_media_draft(self.media_draft)

    def _build_ui(self, input_query):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(14)

        self.search_input = QLineEdit(self)
        self.search_input.setText(input_query or "")
        self.search_input.setFixedHeight(32)

        self.search_button = QPushButton("Find Media", self)
        self.search_button.setMinimumHeight(32)
        self.search_button.setFixedWidth(DETAIL_BUTTON_WIDTH)
        self.search_button.clicked.connect(self.search_media)

        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(16)
        search_layout.addWidget(self.search_input, stretch=1)
        search_layout.addWidget(self.search_button)

        upper_layout = QHBoxLayout()
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(18)

        self.metadata_block = self._build_metadata_block()
        right_column = self._build_right_column()

        upper_layout.addWidget(self.metadata_block, stretch=2)
        upper_layout.addLayout(right_column, stretch=1)

        self.lower_block = self._build_lower_block()
        footer_layout = self._build_footer()

        main_layout.addLayout(search_layout)
        main_layout.addLayout(upper_layout, stretch=1)
        main_layout.addWidget(self.lower_block)
        main_layout.addLayout(footer_layout)

    def _build_metadata_block(self):
        block = DetailBlock("Metadata (via TMDB API)", "details_reload.png", self)
        block.action_button.clicked.connect(self.reload_metadata)

        self.metadata_refresh_status_label = QLabel("", block)
        self.metadata_refresh_status_label.setObjectName("refreshStatus")
        self.metadata_refresh_status_label.hide()
        block.body_layout.addWidget(self.metadata_refresh_status_label)

        self.metadata_scroll = QScrollArea(block)
        self.metadata_scroll.setObjectName("transparentScroll")
        self.metadata_scroll.setWidgetResizable(True)
        self.metadata_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.metadata_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.metadata_content = QWidget()
        self.metadata_content.setObjectName("transparentContent")
        self.metadata_layout = QVBoxLayout(self.metadata_content)
        self.metadata_layout.setContentsMargins(0, 0, 0, 0)
        self.metadata_layout.setSpacing(4)

        self.metadata_scroll.setWidget(self.metadata_content)
        block.body_layout.addWidget(self.metadata_scroll)
        return block

    def _build_right_column(self):
        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(14)

        self.providers_block = DetailBlock("Watch Providers (via TMDB API / JustWatch)", "details_reload.png", self)
        self.providers_block.action_button.clicked.connect(self.reload_watch_providers)

        self.providers_scroll = QScrollArea(self.providers_block)
        self.providers_scroll.setObjectName("transparentScroll")
        self.providers_scroll.setWidgetResizable(True)
        self.providers_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.providers_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.providers_content = QWidget()
        self.providers_content.setObjectName("transparentContent")
        self.providers_layout = QVBoxLayout(self.providers_content)
        self.providers_layout.setContentsMargins(0, 0, 0, 0)
        self.providers_layout.setSpacing(4)
        self.providers_scroll.setWidget(self.providers_content)
        self.providers_block.body_layout.addWidget(self.providers_scroll)

        self.posters_block = DetailBlock("Posters", "details_edit.png", self)
        self.posters_block.action_button.clicked.connect(self.edit_posters)
        self.poster_status_label = QLabel(self.posters_block)
        self.posters_block.body_layout.addWidget(self.poster_status_label)

        self.poster_scroll = QScrollArea(self.posters_block)
        self.poster_scroll.setObjectName("transparentScroll")
        self.poster_scroll.setWidgetResizable(True)
        self.poster_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.poster_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.poster_scroll.setMinimumHeight(POSTER_PREVIEW_HEIGHT)

        self.poster_content = QWidget()
        self.poster_content.setObjectName("transparentContent")
        self.poster_layout = QHBoxLayout(self.poster_content)
        self.poster_layout.setContentsMargins(0, 0, 0, 0)
        self.poster_layout.setSpacing(12)
        self.poster_scroll.setWidget(self.poster_content)
        self.posters_block.body_layout.addWidget(self.poster_scroll, stretch=1)

        right_column.addWidget(self.providers_block)
        right_column.addWidget(self.posters_block, stretch=1)
        return right_column

    def _build_lower_block(self):
        lower_block = QFrame(self)
        lower_block.setObjectName("detailBlock")
        lower_block.setFixedHeight(241)

        lower_layout = QVBoxLayout(lower_block)
        lower_layout.setContentsMargins(16, 14, 16, 14)
        lower_layout.setSpacing(8)

        smart_layout = QHBoxLayout()
        smart_layout.setContentsMargins(0, 0, 0, 0)
        smart_layout.setSpacing(16)

        self.smart_input = QLineEdit(lower_block)
        self.smart_input.setFixedHeight(32)
        self.smart_button = QPushButton("Smart Fill", lower_block)
        self.smart_button.setMinimumHeight(32)
        self.smart_button.setFixedWidth(DETAIL_BUTTON_WIDTH)
        self.smart_button.clicked.connect(self.smart_fill)

        smart_layout.addWidget(self.smart_input, stretch=1)
        smart_layout.addWidget(self.smart_button)
        lower_layout.addLayout(smart_layout)

        columns_layout = QHBoxLayout()
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(28)

        self._add_user_data_panel(columns_layout)
        self.watch_history_layout = self._add_list_panel(
            columns_layout,
            "Watch History",
        )
        self.notes_layout = self._add_list_panel(columns_layout, "Notes")
        self.lists_layout = self._add_list_panel(columns_layout, "Lists")

        lower_layout.addLayout(columns_layout, stretch=1)
        return lower_block

    def _build_footer(self):
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()

        self.delete_button = QPushButton("DELETE", self)
        self.delete_button.setObjectName("deleteButton")
        self.cancel_button = QPushButton("Cancel", self)
        self.save_button = QPushButton("Save", self)

        for button in (self.delete_button, self.cancel_button, self.save_button):
            button.setMinimumHeight(32)
            button.setFixedWidth(DETAIL_BUTTON_WIDTH)
            footer_layout.addWidget(button)

        footer_layout.addStretch()

        self.delete_button.clicked.connect(self.delete_media)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.save_media)

        return footer_layout

    def _add_list_panel(self, parent_layout, title):
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(3)

        title_label = QLabel(title, self)
        title_label.setObjectName("sectionTitle")

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(4)
        scroll.setWidget(content)

        panel_layout.addWidget(title_label)
        panel_layout.addWidget(scroll, stretch=1)
        parent_layout.addLayout(panel_layout, stretch=1)

        return content_layout

    def _add_user_data_panel(self, parent_layout):
        panel_widget = QWidget(self)
        panel_widget.setFixedWidth(190)

        panel_layout = QVBoxLayout(panel_widget)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(4)

        self.status_combo = self._make_combo(
            panel_widget,
            self._on_status_index_changed,
        )
        self.status_combo.activated.connect(self._on_status_activated)
        self.impression_combo = self._make_combo(panel_widget)
        self.collection_combo = self._make_combo(panel_widget)

        self._add_combo_row(panel_layout, "Status", self.status_combo)
        self._add_combo_row(panel_layout, "Impression", self.impression_combo)
        self._add_combo_row(panel_layout, "Collection Pick", self.collection_combo)
        panel_layout.addStretch()

        parent_layout.addWidget(panel_widget, stretch=0)

    def _make_combo(self, parent, change_handler=None):
        combo = DownwardComboBox(parent)
        combo.setMinimumHeight(30)
        combo.setFixedWidth(190)
        view = ComboPopupView(combo)
        view.setItemDelegate(ComboPopupItemDelegate(combo, view))
        combo.setView(view)
        combo.currentIndexChanged.connect(change_handler or self.mark_dirty)
        return combo

    def _add_combo_row(self, parent_layout, label_text, combo):
        label = QLabel(label_text, self)
        parent_layout.addWidget(label)
        parent_layout.addWidget(combo)

    def _load_all_lists(self):
        with get_connection() as conn:
            self.all_lists = media_repo.get_all_lists(conn)

    def set_media_draft(self, media_draft):
        self.media_draft = deepcopy(media_draft)
        self._baseline_media_draft = deepcopy(self.media_draft)
        self._is_dirty = self.media_draft.get("media_id") is None
        self._render_all()
        self._update_action_buttons()

    def _render_all(self):
        self._is_populating = True
        try:
            self.render_metadata()
            self.render_watch_providers()
            self.render_posters()
            self.render_user_data_controls()
            self.render_watch_history()
            self.render_notes()
            self.render_lists()
        finally:
            self._is_populating = False

    def render_metadata(self):
        clear_layout(self.metadata_layout)

        for row in build_metadata_display_rows(self.media_draft):
            label = QLabel(self.metadata_content)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            label.setWordWrap(False)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setOpenExternalLinks(True)
            label.setText(row["text"])

            if row.get("tooltip"):
                label.setToolTip(row["tooltip"])

            self.metadata_layout.addWidget(label)

        self.metadata_layout.addStretch()

    def render_watch_providers(self):
        clear_layout(self.providers_layout)
        grouped = group_watch_providers(self.media_draft.get("watch_providers", []))

        for access_type, label in WATCH_PROVIDER_GROUPS:
            value = ", ".join(grouped.get(access_type, [])) or "None"
            provider_label = QLabel(f"{label}: {value}", self.providers_content)
            provider_label.setWordWrap(False)
            provider_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.providers_layout.addWidget(provider_label)

        metadata = self.media_draft.get("metadata") or {}
        checked_at = format_watch_provider_checked_at(
            metadata.get("last_tmdb_watch_providers_checked_at"),
        )
        checked_at_label = QLabel(
            f"Last Sync: {checked_at or 'None'}",
            self.providers_content,
        )
        checked_at_label.setWordWrap(False)
        checked_at_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.providers_layout.addWidget(checked_at_label)

        self.providers_layout.addStretch()
        self.providers_content.adjustSize()

    def render_posters(self):
        clear_layout(self.poster_layout)

        posters = self.media_draft.get("posters", [])
        self.poster_status_label.setText(get_poster_curation_status(posters))

        if not posters:
            self.poster_layout.addWidget(QLabel("No posters", self.poster_content))
            self.poster_layout.addStretch()
            return

        for poster in posters:
            label = QLabel(self.poster_content)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(POSTER_PREVIEW_HEIGHT)
            label.setMinimumWidth(96)

            pixmap = load_poster_pixmap(poster)

            if pixmap is None or pixmap.isNull():
                label.setText(poster.get("filename") or "Poster")
                label.setWordWrap(True)
                label.setFixedWidth(110)
            else:
                scaled = pixmap.scaledToHeight(
                    POSTER_PREVIEW_HEIGHT,
                    Qt.TransformationMode.SmoothTransformation,
                )
                label.setFixedSize(scaled.size())
                label.setPixmap(scaled)

            self.poster_layout.addWidget(label)

        self.poster_layout.addStretch()

    def render_user_data_controls(self):
        user_data = self.media_draft.get("user_data") or {}
        metadata = self.media_draft.get("metadata") or {}
        self._status_change_generation += 1
        populate_status_combo(
            self.status_combo,
            metadata.get("media_type"),
            user_data.get("watch_state"),
        )
        self.status_combo.reset_user_activation_baseline()
        populate_combo(self.impression_combo, IMPRESSION_OPTIONS, user_data.get("impression"))
        populate_combo(
            self.collection_combo,
            COLLECTION_PICK_OPTIONS,
            user_data.get("is_collection_pick"),
        )

    def render_watch_history(self):
        clear_layout(self.watch_history_layout)

        for entry in build_watch_history_display_entries(self.media_draft):
            self.watch_history_layout.addLayout(
                self._make_action_line(
                    "details_edit.png",
                    entry["text"],
                    lambda checked=False, entry=entry: self.edit_watch_history(entry),
                )
            )

        self.watch_history_layout.addWidget(
            make_icon_button("details_add.png", self, self.add_watch_history)
        )
        self.watch_history_layout.addStretch()

    def render_notes(self):
        clear_layout(self.notes_layout)

        for note in self.media_draft.get("user_data", {}).get("notes", []):
            self.notes_layout.addLayout(
                self._make_action_line(
                    "details_edit.png",
                    note.get("note") or "",
                    self.edit_note,
                )
            )

        self.notes_layout.addWidget(make_icon_button("details_add.png", self, self.add_note))
        self.notes_layout.addStretch()

    def render_lists(self):
        clear_layout(self.lists_layout)
        self.list_checkboxes = []

        selected_lists = self.media_draft.get("user_data", {}).get("lists", [])
        selected_by_id = {
            item.get("id"): item
            for item in selected_lists
            if item.get("id") is not None
        }
        selected_names = {
            item.get("name")
            for item in selected_lists
            if item.get("name")
        }

        lists_to_show = list(self.all_lists)
        known_ids = {item.get("id") for item in lists_to_show}

        for selected in selected_lists:
            if selected.get("id") not in known_ids and selected.get("name"):
                lists_to_show.append({
                    "id": selected.get("id"),
                    "name": selected.get("name"),
                    "description": None,
                })

        for list_item in lists_to_show:
            checkbox = QCheckBox(list_item["name"], self)
            checkbox.setChecked(
                list_item.get("id") in selected_by_id
                or list_item.get("name") in selected_names
            )
            checkbox.stateChanged.connect(self.mark_dirty)
            self.list_checkboxes.append((checkbox, list_item))
            self.lists_layout.addWidget(checkbox)

        self.lists_layout.addWidget(make_icon_button("details_add.png", self, self.add_list))
        self.lists_layout.addStretch()

    def _make_action_line(self, icon_name, text, callback):
        line_layout = QHBoxLayout()
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(DETAIL_ACTION_LINE_ICON_TEXT_SPACING)

        line_layout.addWidget(make_icon_button(icon_name, self, callback))

        label = QLabel(text, self)
        label.setWordWrap(False)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        line_layout.addWidget(label, stretch=1)

        return line_layout

    def mark_dirty(self):
        if self._is_populating:
            return

        self._is_dirty = True
        self._update_action_buttons()

    def _on_status_index_changed(self, _index):
        self._status_change_generation += 1
        self.mark_dirty()

    def _on_status_activated(self, _index):
        previous_status = (
            self.status_combo.take_user_activation_previous_data()
        )
        current_status = self.status_combo.currentData()

        if previous_status == "watched" or current_status != "watched":
            return

        self._schedule_new_watch_entry_dialog()

    def _schedule_new_watch_entry_dialog(self):
        if (
            self._is_populating
            or self._metadata_refresh_in_progress
            or self._is_closing
            or self._watch_entry_dialog_active
        ):
            return

        generation = self._status_change_generation

        if self._scheduled_watch_entry_generation == generation:
            return

        self._scheduled_watch_entry_generation = generation
        QTimer.singleShot(
            0,
            lambda generation=generation: (
                self._open_scheduled_watch_entry_dialog(generation)
            ),
        )

    def _open_scheduled_watch_entry_dialog(self, generation):
        if self._scheduled_watch_entry_generation == generation:
            self._scheduled_watch_entry_generation = None

        if (
            generation != self._status_change_generation
            or self.status_combo.currentData() != "watched"
            or self._is_populating
            or self._metadata_refresh_in_progress
            or self._is_closing
            or self._watch_entry_dialog_active
        ):
            return

        active_modal = QApplication.activeModalWidget()

        if active_modal is not None and active_modal is not self:
            return

        self._open_watch_entry_details()

    def _update_action_buttons(self):
        has_media_id = self.media_draft.get("media_id") is not None
        self.delete_button.setEnabled(has_media_id)
        self.save_button.setEnabled(not has_media_id or self._is_dirty)

    def search_media(self):
        if self._metadata_refresh_in_progress:
            return

        if self._is_dirty:
            result = QMessageBox.question(
                self,
                "Discard changes?",
                "Find Media will replace the current draft and discard unsaved changes.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if result != QMessageBox.Yes:
                return

        media_draft = resolve_media_draft_from_query(self, self.search_input.text())

        if media_draft is None:
            return

        self._load_all_lists()
        self.set_media_draft(media_draft)

    def reject(self):
        self._cancel_active_metadata_refresh()
        super().reject()

    def accept(self):
        self._cancel_active_metadata_refresh()
        super().accept()

    def closeEvent(self, event):
        self._cancel_active_metadata_refresh()
        super().closeEvent(event)

    def _cancel_active_metadata_refresh(self):
        self._is_closing = True

        if self._metadata_refresh_job_id is not None:
            self.metadata_refresh_manager.cancel(self._metadata_refresh_job_id)

    def reload_metadata(self):
        if self._metadata_refresh_in_progress:
            return

        self._apply_form_to_draft()
        match = build_tmdb_match_from_metadata(
            self.media_draft.get("metadata") or {}
        )

        try:
            job_id = self.metadata_refresh_manager.start_refresh(
                self.media_draft.get("media_id"),
                match,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Metadata", str(exc))
            return

        self._metadata_refresh_job_id = job_id
        self._set_metadata_refresh_busy(True, "Refreshing metadata…")

    def _on_metadata_refresh_progress(self, job_id, payload):
        if not self._is_current_metadata_refresh(job_id):
            return

        message = (payload or {}).get("message") or "Refreshing metadata…"
        self.metadata_refresh_status_label.setText(message)

    def _on_metadata_refresh_succeeded(self, job_id, payload):
        if not self._is_current_metadata_refresh(job_id) or self._is_closing:
            return

        was_dirty = self._is_dirty

        try:
            refreshed_draft = merge_metadata_refresh(self.media_draft, payload)
            refreshed_baseline = merge_metadata_refresh(
                self._baseline_media_draft,
                payload,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Metadata", str(exc))
            return

        self.media_draft = refreshed_draft
        self._baseline_media_draft = refreshed_baseline
        self._is_dirty = was_dirty
        self._render_all()
        self._update_action_buttons()

        refresh_result = (payload or {}).get("refresh_result") or {}
        stats = refresh_result.get("stats") or {}
        created = stats.get("created", stats.get("episodes_created", 0)) or 0
        preserved = stats.get(
            "preserved_missing",
            stats.get("local_absent_preserved", 0),
        ) or 0

        if created or preserved:
            parts = []

            if created:
                parts.append(f"{created} new episode(s) added")

            if preserved:
                parts.append(f"{preserved} local episode(s) preserved")

            QMessageBox.information(self, "Metadata", ". ".join(parts) + ".")

    def _on_metadata_refresh_failed(self, job_id, payload):
        if not self._is_current_metadata_refresh(job_id) or self._is_closing:
            return

        QMessageBox.warning(
            self,
            "Metadata",
            (payload or {}).get("message") or "Metadata refresh failed.",
        )

    def _on_metadata_refresh_cancelled(self, job_id, payload):
        if not self._is_current_metadata_refresh(job_id):
            return

        self.metadata_refresh_status_label.setText("Metadata refresh cancelled.")

    def _on_metadata_refresh_finished(self, job_id, payload):
        if not self._is_current_metadata_refresh(job_id):
            return

        self._metadata_refresh_job_id = None
        self._set_metadata_refresh_busy(False)

    def _is_current_metadata_refresh(self, job_id):
        return job_id == self._metadata_refresh_job_id

    def _set_metadata_refresh_busy(self, is_busy, message=None):
        self._metadata_refresh_in_progress = is_busy
        self.metadata_block.action_button.setEnabled(not is_busy)
        self.providers_block.action_button.setEnabled(not is_busy)
        self.posters_block.action_button.setEnabled(not is_busy)
        self.search_input.setEnabled(not is_busy)
        self.search_button.setEnabled(not is_busy)
        self.lower_block.setEnabled(not is_busy)

        if is_busy:
            self.metadata_refresh_status_label.setText(
                message or "Refreshing metadata…"
            )
            self.metadata_refresh_status_label.show()
            self.save_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return

        self.metadata_refresh_status_label.hide()
        self._update_action_buttons()

    def reload_watch_providers(self):
        if self._metadata_refresh_in_progress:
            return

        try:
            providers = tmdb_fetcher.get_tmdb_media_watch_providers(
                build_tmdb_match_from_metadata(self.media_draft.get("metadata") or {})
            )
        except Exception as exc:
            QMessageBox.warning(self, "Watch Providers", str(exc))
            return

        checked_at = tmdb_fetcher.current_sqlite_timestamp()
        metadata = self.media_draft.setdefault("metadata", {})
        metadata["last_tmdb_watch_providers_checked_at"] = checked_at
        self.media_draft["watch_providers"] = providers
        media_id = self.media_draft.get("media_id")

        if media_id is not None:
            try:
                with get_connection() as conn:
                    media_repo.replace_media_watch_providers(
                        conn,
                        media_id,
                        providers,
                        checked_at=checked_at,
                    )
            except Exception as exc:
                QMessageBox.warning(self, "Watch Providers", str(exc))
                return

            baseline_metadata = self._baseline_media_draft.setdefault(
                "metadata",
                {},
            )
            baseline_metadata["last_tmdb_watch_providers_checked_at"] = checked_at
            self._baseline_media_draft["watch_providers"] = deepcopy(providers)
        else:
            self._is_dirty = True

        self.render_watch_providers()
        self._update_action_buttons()

    def edit_posters(self):
        print("Poster edit clicked")

    def smart_fill(self):
        print("Smart Fill clicked")

    def edit_watch_history(self, entry=None):
        self._open_watch_entry_details(entry)

    def add_watch_history(self):
        self._open_watch_entry_details()

    def _open_watch_entry_details(self, entry=None):
        if self._watch_entry_dialog_active:
            return

        self._watch_entry_dialog_active = True

        try:
            dialog = WatchEntryDetailsDialog(self, self.media_draft, entry)
            result = dialog.exec()
        finally:
            self._watch_entry_dialog_active = False

        if result != QDialog.Accepted:
            return

        apply_watch_entry_result(
            self.media_draft,
            entry,
            dialog.result_payload,
        )

        if self._is_episode():
            user_data = self.media_draft.setdefault("user_data", {})
            watch_history = user_data.get("watch_history") or []
            action = dialog.result_payload.get("action")

            if entry is None and action == "save" and watch_history:
                user_data["watch_state"] = "watched"
                set_combo_value(self.status_combo, "watched")
            elif action == "delete" and not watch_history:
                current_watch_state = self.status_combo.currentData()

                if current_watch_state == "watched":
                    current_watch_state = None
                    set_combo_value(self.status_combo, None)

                user_data["watch_state"] = current_watch_state

        self.mark_dirty()
        self.render_watch_history()

    def edit_note(self):
        print("Note edit clicked")

    def add_note(self):
        print("Note add clicked")

    def add_list(self):
        print("List add clicked")

    def save_media(self):
        if self._metadata_refresh_in_progress:
            return

        self._apply_form_to_draft()
        media_id = self.media_draft.get("media_id")

        try:
            if media_id is None:
                draft_to_save = deepcopy(self.media_draft)

                with get_connection() as conn:
                    save_result = draft_saver.save_media_draft_with_posters(
                        conn,
                        draft_to_save,
                    )

                self.media_draft = draft_to_save
            else:
                with get_connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    save_result = draft_saver.save_existing_media_changes(
                        conn,
                        self._baseline_media_draft,
                        self.media_draft,
                    )

                apply_inserted_ids_to_draft(self.media_draft, save_result)
        except Exception as exc:
            QMessageBox.warning(self, "Save Media", str(exc))
            return

        self._baseline_media_draft = deepcopy(self.media_draft)

        self.result_payload = {
            "status": "saved",
            "media_id": save_result["media_id"],
            "media_draft": self.media_draft,
            "save_result": save_result,
        }
        self.accept()

    def delete_media(self):
        if self._metadata_refresh_in_progress:
            return

        media_id = self.media_draft.get("media_id")

        if media_id is None:
            return

        metadata = self.media_draft.get("metadata") or {}
        title = metadata.get("title") or "this media"
        result = QMessageBox.warning(
            self,
            "Delete Media",
            f"Delete {title} from the database?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if result != QMessageBox.Yes:
            return

        try:
            with get_connection() as conn:
                deleted = media_repo.delete_media(conn, media_id)
        except Exception as exc:
            QMessageBox.warning(self, "Delete Media", str(exc))
            return

        if not deleted:
            QMessageBox.warning(self, "Delete Media", "This media no longer exists.")
            return

        self.result_payload = {
            "status": "deleted",
            "media_id": media_id,
            "media_draft": self.media_draft,
        }
        self.accept()

    def _apply_form_to_draft(self):
        user_data = deepcopy(self.media_draft.get("user_data") or {})
        user_data["watch_state"] = self.status_combo.currentData()

        if self._is_episode() and user_data["watch_state"] == "watched":
            watch_history = user_data.setdefault("watch_history", [])

            if not watch_history:
                watch_history.append({
                    "draft_id": make_draft_id(),
                    "date_earliest": None,
                    "date_latest": None,
                })

        user_data["impression"] = self.impression_combo.currentData()
        user_data["is_collection_pick"] = self.collection_combo.currentData()
        user_data["lists"] = self._collect_selected_lists(user_data.get("lists", []))
        self.media_draft["user_data"] = user_data

    def _is_episode(self):
        return (
            (self.media_draft.get("metadata") or {}).get("media_type")
            == "episode"
        )

    def _collect_selected_lists(self, current_lists):
        selected_lists = []

        for checkbox, list_item in self.list_checkboxes:
            if not checkbox.isChecked():
                continue

            selected_lists.append({
                "id": list_item.get("id"),
                "name": list_item.get("name"),
            })

        return selected_lists

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #f1f1f1;
            }

            QLabel {
                color: black;
                font-size: 12px;
                background: transparent;
                margin: 0px;
                padding: 1px 0px;
            }

            QLabel#blockTitle,
            QLabel#sectionTitle {
                font-size: 12px;
                font-weight: normal;
            }

            QFrame#detailBlock {
                background-color: #f1f1f1;
                border: 1px solid #555555;
            }

            QLineEdit {
                border: 1px solid #bcbcbc;
                border-radius: 6px;
                padding: 4px 8px;
                background-color: white;
                color: black;
                font-size: 12px;
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

            QPushButton:disabled {
                color: #888888;
                border-color: #999999;
            }

            QPushButton#deleteButton {
                color: red;
            }

            QPushButton#deleteButton:disabled {
                color: #888888;
            }

            QComboBox {
                background-color: white;
                color: black;
                border: 1px solid #bcbcbc;
                border-radius: 6px;
                padding: 4px 28px 4px 8px;
                font-size: 12px;
                min-height: 22px;
            }

            QComboBox:hover {
                background-color: #f2f2f2;
            }

            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #d0d0d0;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }

            QComboBox::down-arrow {
                image: url(app/assets/dropdown_arrow.svg);
                width: 10px;
                height: 10px;
            }

            QComboBox QAbstractItemView {
                background-color: white;
                color: black;
                border: none;
                outline: 0px;
                selection-background-color: #f2f2f2;
                selection-color: black;
            }

            QComboBox QAbstractItemView::item {
                min-height: 30px;
                padding: 5px 8px;
            }

            QComboBox QAbstractItemView::item:hover,
            QComboBox QAbstractItemView::item:selected {
                background-color: #f2f2f2;
                color: black;
            }

            QScrollArea {
                background: transparent;
                border: none;
            }

            QScrollArea#transparentScroll,
            QScrollArea#transparentScroll > QWidget,
            QScrollArea#transparentScroll > QWidget > QWidget,
            QWidget#transparentContent {
                background-color: #f1f1f1;
            }

            QCheckBox {
                color: black;
                font-size: 12px;
                background: transparent;
                margin: 0px;
                padding: 1px 0px;
            }

            QToolButton {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)


def make_icon_button(icon_name, parent=None, callback=None):
    button = QToolButton(parent)
    button.setFixedSize(DETAIL_ICON_BUTTON_SIZE, DETAIL_ICON_BUTTON_SIZE)
    button.setIcon(QIcon(str(DETAIL_ICON_DIR / icon_name)))
    button.setIconSize(QSize(DETAIL_ICON_SIZE, DETAIL_ICON_SIZE))
    button.setCursor(Qt.CursorShape.PointingHandCursor)

    if callback is not None:
        button.clicked.connect(callback)

    return button


def populate_combo(combo, options, current_value):
    combo.blockSignals(True)
    combo.clear()

    for value, label in options:
        combo.addItem(label, value)

    set_combo_value(combo, current_value)
    combo.blockSignals(False)


def populate_status_combo(combo, media_type, current_value):
    options = STATUS_OPTIONS_BY_MEDIA_TYPE.get(
        media_type,
        ((None, "Not in watchlist"),),
    )
    populate_combo(combo, options, current_value)


def set_combo_value(combo, value):
    index = combo.findData(value)

    if index >= 0:
        combo.setCurrentIndex(index)
        return

    if combo.count():
        combo.setCurrentIndex(0)


def load_poster_pixmap(poster):
    filename = poster.get("filename")

    if not filename:
        return None

    normalized_filename = filename.lstrip("/")
    local_path = POSTER_DIR / normalized_filename

    if local_path.exists():
        pixmap = QPixmap(str(local_path))
        return pixmap if not pixmap.isNull() else None

    if poster.get("source", "tmdb") != "tmdb":
        return None

    try:
        response = requests.get(
            f"{TMDB_IMAGE_BASE_URL}/{TMDB_POSTER_PREVIEW_SIZE}/{normalized_filename}",
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    pixmap = QPixmap()

    if not pixmap.loadFromData(response.content):
        return None

    return pixmap


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        widget = item.widget()

        if child_layout is not None:
            clear_layout(child_layout)

        if widget is not None:
            widget.deleteLater()
