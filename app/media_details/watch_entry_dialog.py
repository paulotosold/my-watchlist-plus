from copy import deepcopy

from PySide6.QtCore import QDate, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .calendar_picker import CleanCalendarPopup
from .constants import (
    DETAIL_BUTTON_WIDTH,
    DETAILS_BACKGROUND_COLOR,
    DETAIL_ICON_DIR,
)
from app.media_details_formatters import (
    format_episode_ranges,
    format_watch_history_entry,
)
from app.media_state_controls import ClickableEntryLabel
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
    episode_key,
    get_series_episodes,
    is_episode_available,
    validate_watch_dates,
    watched_episode_keys,
)


WATCH_ENTRY_DIALOG_DEFAULT_WIDTH = 960
WATCH_ENTRY_DIALOG_MAX_HEIGHT = 750
WATCH_ENTRY_EPISODE_SELECTOR_MAX_HEIGHT = 520
WATCH_ENTRY_DATE_GROUP_SPACING = 2
WATCH_ENTRY_INLINE_BUTTON_SIZE = 32
WATCH_ENTRY_INLINE_ICON_SIZE = 20
WATCH_ENTRY_SEASON_LABEL_WIDTH = 60
WATCH_ENTRY_SEASON_LABEL_BUTTON_SPACING = 20


class WatchEntryDetailsDialog(QDialog):
    def __init__(self, parent, media_draft, entry=None):
        super().__init__(parent)

        self.media_draft = deepcopy(media_draft)
        self.entry = deepcopy(entry) if entry is not None else None
        self.result_payload = {"action": "cancel"}
        self.episode_buttons = {}
        self.season_labels = {}
        self.season_episode_keys = {}
        self.initial_signature = None
        self._date_picker_popup = None

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
            QScrollArea#episodeSelectorScroll,
            QScrollArea#episodeSelectorScroll > QWidget,
            QScrollArea#episodeSelectorScroll > QWidget > QWidget,
            QWidget#episodeSelectorContent,
            QFrame#dialogButtonBar {{
                background-color: {DETAILS_BACKGROUND_COLOR};
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

            QToolButton#watchEntryInlineButton {{
                background-color: white;
                border: 1px solid #bcbcbc;
                border-radius: 6px;
                padding: 3px;
            }}

            QToolButton#watchEntryInlineButton:hover {{
                background-color: #f2f2f2;
            }}
        """)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(0)

        date_layout = QHBoxLayout()
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(8)

        self.date_earliest_input = self._make_date_input()
        self.date_latest_input = self._make_date_input()
        self.date_earliest_picker_button = self._make_inline_icon_button(
            "watch_history_calendar_picker.png",
            "Choose earliest date",
            lambda: self._open_date_picker(
                self.date_earliest_input,
                self.date_earliest_picker_button,
            ),
        )
        self.copy_date_button = self._make_inline_icon_button(
            "watch_history_copy_over.png",
            "Copy earliest date to latest date",
            self._copy_earliest_to_latest,
        )
        self.date_latest_picker_button = self._make_inline_icon_button(
            "watch_history_calendar_picker.png",
            "Choose latest date",
            lambda: self._open_date_picker(
                self.date_latest_input,
                self.date_latest_picker_button,
            ),
        )
        self.preview_label = QLabel(self)
        self.preview_label.setWordWrap(False)

        date_layout.addWidget(QLabel("Earliest Date:", self))
        date_layout.addWidget(self.date_earliest_input)
        date_layout.addWidget(self.date_earliest_picker_button)
        date_layout.addWidget(self.copy_date_button)
        date_layout.addSpacing(WATCH_ENTRY_DATE_GROUP_SPACING)
        date_layout.addWidget(QLabel("Latest Date:", self))
        date_layout.addWidget(self.date_latest_input)
        date_layout.addWidget(self.date_latest_picker_button)
        date_layout.addSpacing(WATCH_ENTRY_DATE_GROUP_SPACING)
        date_layout.addWidget(self.preview_label, stretch=1)
        main_layout.addLayout(date_layout)

        if self._is_series():
            main_layout.addSpacing(WATCH_ENTRY_HEADER_TO_EPISODES_SPACING)
            main_layout.addWidget(self._build_episode_selector())
            main_layout.addSpacing(WATCH_ENTRY_EPISODES_TO_BUTTONS_SPACING)
        else:
            main_layout.addSpacing(WATCH_ENTRY_HEADER_TO_BUTTONS_SPACING)

        main_layout.addWidget(self._build_button_bar())

    def _make_date_input(self):
        input_widget = QLineEdit(self)
        input_widget.setFixedHeight(32)
        input_widget.setFixedWidth(WATCH_ENTRY_DATE_INPUT_WIDTH)
        input_widget.setClearButtonEnabled(True)
        input_widget.textChanged.connect(self._refresh_state)
        return input_widget

    def _make_inline_icon_button(self, icon_name, tooltip, callback):
        button = QToolButton(self)
        button.setObjectName("watchEntryInlineButton")
        button.setFixedSize(
            WATCH_ENTRY_INLINE_BUTTON_SIZE,
            WATCH_ENTRY_INLINE_BUTTON_SIZE,
        )
        button.setIcon(QIcon(str(DETAIL_ICON_DIR / icon_name)))
        button.setIconSize(
            QSize(
                WATCH_ENTRY_INLINE_ICON_SIZE,
                WATCH_ENTRY_INLINE_ICON_SIZE,
            )
        )
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _copy_earliest_to_latest(self):
        self.date_latest_input.setText(self.date_earliest_input.text())

    def _open_date_picker(self, target_input, anchor_button):
        self._close_date_picker_popup()

        input_text = target_input.text().strip()
        initial_date = QDate.fromString(input_text, "yyyy-MM-dd")

        if (
            not initial_date.isValid()
            or initial_date.toString("yyyy-MM-dd") != input_text
        ):
            initial_date = QDate.currentDate()

        popup = CleanCalendarPopup(initial_date=initial_date, parent=self)
        self._date_picker_popup = popup
        popup.date_selected.connect(
            lambda date, popup=popup, target_input=target_input: (
                self._apply_picker_date(popup, target_input, date)
            )
        )
        popup.destroyed.connect(
            lambda _object=None, popup=popup: self._clear_date_picker_popup(
                popup
            )
        )
        popup.ensurePolished()
        popup.layout().activate()
        popup.adjustSize()
        popup.move(self._date_picker_position(popup, anchor_button))
        popup.show()

    def _date_picker_position(self, popup, anchor_button):
        anchor_bottom = anchor_button.mapToGlobal(
            QPoint(0, anchor_button.height() + 6)
        )
        screen = anchor_button.screen()

        if screen is None:
            return anchor_bottom

        available = screen.availableGeometry()
        x = min(
            max(anchor_bottom.x(), available.left()),
            available.right() - popup.width() + 1,
        )
        y = anchor_bottom.y()

        if y + popup.height() > available.bottom() + 1:
            anchor_top = anchor_button.mapToGlobal(QPoint(0, 0))
            y = anchor_top.y() - popup.height() - 6

        y = min(
            max(y, available.top()),
            available.bottom() - popup.height() + 1,
        )
        return QPoint(x, y)

    def _apply_picker_date(self, popup, target_input, date):
        if popup is not self._date_picker_popup:
            return

        target_input.setText(date.toString("yyyy-MM-dd"))
        self._date_picker_popup = None
        QTimer.singleShot(0, popup.close)

    def _clear_date_picker_popup(self, popup):
        if self._date_picker_popup is popup:
            self._date_picker_popup = None

    def _close_date_picker_popup(self):
        popup = self._date_picker_popup
        self._date_picker_popup = None

        if popup is not None:
            popup.close()

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

                self.season_episode_keys[season_num] = []
                season_label = ClickableEntryLabel(
                    f"Season {season_num}:",
                    self,
                    lambda season_num=season_num: self._toggle_season(
                        season_num
                    ),
                )
                season_label.setFixedWidth(WATCH_ENTRY_SEASON_LABEL_WIDTH)
                season_label.setSizePolicy(
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
                season_label.setAccessibleName(f"Season {season_num}")
                self.season_labels[season_num] = season_label
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
                    self.season_episode_keys[season_num].append(key)
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
        self.save_entry_button.setDefault(True)

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

    def _toggle_season(self, season_num):
        enabled_buttons = [
            self.episode_buttons[key][0]
            for key in self.season_episode_keys.get(season_num, [])
            if self.episode_buttons[key][0].isEnabled()
        ]

        if not enabled_buttons:
            return

        should_select = not all(
            button.isChecked()
            for button in enabled_buttons
        )

        for button in enabled_buttons:
            button.setChecked(should_select)

        self._refresh_state()

    def _refresh_state(self):
        validation = self._validated_dates()
        self.preview_label.setText(f"Preview: {self._preview_text(validation)}")

        for key in self.episode_buttons:
            self._refresh_episode_button(key)

        for season_num in self.season_labels:
            self._refresh_season_label(season_num)

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

    def _refresh_season_label(self, season_num):
        label = self.season_labels[season_num]
        enabled_buttons = [
            self.episode_buttons[key][0]
            for key in self.season_episode_keys.get(season_num, [])
            if self.episode_buttons[key][0].isEnabled()
        ]
        label.setEnabled(bool(enabled_buttons))

        if not enabled_buttons:
            label.setToolTip(
                f"No available episodes can be changed in Season {season_num}."
            )
            label.setAccessibleDescription(label.toolTip())
            return

        if all(button.isChecked() for button in enabled_buttons):
            tooltip = f"Clear all available episodes in Season {season_num}."
        else:
            tooltip = f"Select all available episodes in Season {season_num}."

        label.setToolTip(tooltip)
        label.setAccessibleDescription(tooltip)

    def _validated_dates(self):
        return validate_watch_dates(
            self.date_earliest_input.text(),
            self.date_latest_input.text(),
        )

    def _preview_text(self, validation=None):
        validation = validation or self._validated_dates()

        if not validation["is_valid"]:
            if validation["error_type"] == "invalid_range":
                return "Invalid range — check date order"

            return "Invalid date — use YYYY-MM-DD"

        event = {
            "date_earliest": validation["date_earliest"],
            "date_latest": validation["date_latest"],
            "created_at": (
                (self.entry or {}).get("created_at")
                or QDate.currentDate().toString("yyyy-MM-dd")
            ),
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

    def done(self, result):
        self._close_date_picker_popup()
        super().done(result)
