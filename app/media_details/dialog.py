from __future__ import annotations

from copy import deepcopy

import requests

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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

import app.media_draft.saver as draft_saver
import app.media_draft.poster_storage as poster_storage
import app.media_repository as media_repo
import app.tmdb as tmdb
from .constants import (
    DETAIL_BUTTON_WIDTH,
    DETAIL_ICON_BUTTON_SIZE,
    POSTER_DIR,
)
from .list_dialog import ListDetailsDialog
from .note_dialog import (
    NoteDetailsDialog,
    NotePreviewLabel,
)
from .poster_dialog import ManagePostersDialog, POSTER_MANAGEMENT_KEY
from .watch_entry_dialog import WatchEntryDetailsDialog
from .widgets import (
    DetailBlock,
    clear_layout,
    make_icon_button,
)
from app.media_draft import (
    apply_inserted_ids_to_draft,
    merge_metadata_refresh,
)
from app.metadata_refresh import get_metadata_refresh_manager
from app.watch_provider_refresh import get_watch_provider_refresh_manager
from .formatters import (
    WATCH_PROVIDER_GROUPS,
    build_metadata_display_rows,
    build_tmdb_match_from_metadata,
    format_watch_provider_checked_at,
    get_poster_curation_status,
    group_watch_providers,
)
from app.find_media import resolve_media_draft_from_query
from app.media_user_data.notes import apply_note_result
from app.media_user_data.watch_history import (
    apply_watch_entry_result,
    make_draft_id,
)
from app.media_user_data.watch_history_formatters import (
    build_watch_history_display_entries,
)
from app.ui.clickable_entry_label import ClickableEntryLabel
from app.ui.media_state_controls import (
    COLLECTION_PICK_LABEL,
    COLLECTION_PICK_OPTIONS,
    IMPRESSION_OPTIONS,
    MEDIA_STATE_COMBO_MIN_HEIGHT,
    MEDIA_STATE_COMBO_STYLE,
    MEDIA_STATE_FIELD_SPACING,
    MEDIA_STATE_FIELD_WIDTH,
    ComboPopupItemDelegate,
    ComboPopupView,
    DownwardComboBox,
    populate_combo,
    populate_status_combo,
    set_combo_value,
)
from app.ui.top_bar import FIND_MEDIA_INPUT_PLACEHOLDER, INPUT_BOX_STYLE
from db.connection import get_connection


TMDB_POSTER_PREVIEW_SIZE = "w185"
POSTER_PREVIEW_HEIGHT = 232
ENTRY_ACTION_LINE_HEIGHT = DETAIL_ICON_BUTTON_SIZE
LIST_CHECKBOX_SIZE = ENTRY_ACTION_LINE_HEIGHT
LIST_CHECKBOX_TO_TEXT_SPACING = 8
DETAIL_BLOCK_SPACING = 14
REFRESH_FEEDBACK_DURATION_MS = 500


def open_media_details_dialog(parent, media_draft, media_query=None):
    dialog = MediaDetailsDialog(
        parent=parent,
        media_draft=media_draft,
        media_query=media_query,
    )

    dialog.exec()
    return dialog.result_payload


class MediaDetailsDialog(QDialog):
    def __init__(
        self,
        parent,
        media_draft,
        media_query=None,
        metadata_refresh_manager=None,
        watch_provider_refresh_manager=None,
        auto_refresh_watch_providers=True,
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
        self._metadata_refresh_completed_successfully = False
        self._watch_provider_refresh_job_id = None
        self._watch_provider_refresh_target_media_id = None
        self._watch_provider_refresh_in_progress = False
        self._watch_provider_refresh_is_manual = False
        self._watch_provider_refresh_completed_successfully = False
        self._auto_refresh_watch_providers = auto_refresh_watch_providers
        self._auto_refreshed_watch_provider_media_ids = set()
        self._is_closing = False
        self._watch_entry_dialog_active = False
        self._status_change_generation = 0
        self._scheduled_watch_entry_generation = None
        self._status_change_previous_dirty = False
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
        self.watch_provider_refresh_manager = (
            watch_provider_refresh_manager
            or get_watch_provider_refresh_manager()
        )
        self.watch_provider_refresh_manager.succeeded.connect(
            self._on_watch_provider_refresh_succeeded
        )
        self.watch_provider_refresh_manager.failed.connect(
            self._on_watch_provider_refresh_failed
        )
        self.watch_provider_refresh_manager.cancelled.connect(
            self._on_watch_provider_refresh_cancelled
        )
        self.watch_provider_refresh_manager.finished.connect(
            self._on_watch_provider_refresh_finished
        )

        self.setWindowTitle("Media Details")
        self.setFixedSize(1320, 810)

        self._load_all_lists()
        self._build_ui(media_query)
        self._apply_styles()
        self.set_media_draft(self.media_draft)

    def _build_ui(self, media_query):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(DETAIL_BLOCK_SPACING)

        self.find_media_input = QLineEdit(self)
        self.find_media_input.setClearButtonEnabled(True)
        self.find_media_input.setText(media_query or "")
        self.find_media_input.setFixedHeight(32)
        self.find_media_input.setPlaceholderText(FIND_MEDIA_INPUT_PLACEHOLDER)
        self.find_media_input.setStyleSheet(INPUT_BOX_STYLE)
        self.find_media_input.returnPressed.connect(self.find_media)

        find_media_layout = QHBoxLayout()
        find_media_layout.setContentsMargins(0, 0, 0, 0)
        find_media_layout.setSpacing(8)
        self.find_media_label = QLabel("Find Media:", self)
        find_media_layout.addWidget(self.find_media_label)
        find_media_layout.addWidget(self.find_media_input, stretch=1)

        upper_layout = QHBoxLayout()
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(DETAIL_BLOCK_SPACING)

        self.metadata_block = self._build_metadata_block()
        right_column = self._build_right_column()

        upper_layout.addWidget(self.metadata_block, stretch=3)
        upper_layout.addLayout(right_column, stretch=2)

        self.lower_block = self._build_lower_block()
        footer_layout = self._build_footer()

        main_layout.addLayout(find_media_layout)
        main_layout.addLayout(upper_layout, stretch=1)
        main_layout.addWidget(self.lower_block)
        main_layout.addLayout(footer_layout)

    def _build_metadata_block(self):
        block = DetailBlock(
            "Metadata (via TMDB API)",
            "details_reload.png",
            self,
            action_tooltip="Refresh metadata",
        )
        block.action_button.clicked.connect(self.reload_metadata)

        self.metadata_refresh_status_label = QLabel("", block)
        self.metadata_refresh_status_label.setObjectName("refreshStatus")
        self.metadata_refresh_status_label.setContentsMargins(5, 0, 0, 0)
        self.metadata_refresh_status_label.hide()
        block.add_header_widget(self.metadata_refresh_status_label)

        self._metadata_refresh_feedback_timer = QTimer(self)
        self._metadata_refresh_feedback_timer.setSingleShot(True)
        self._metadata_refresh_feedback_timer.setInterval(
            REFRESH_FEEDBACK_DURATION_MS
        )
        self._metadata_refresh_feedback_timer.timeout.connect(
            self._hide_metadata_refresh_feedback
        )

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
        right_column.setSpacing(DETAIL_BLOCK_SPACING)

        self.providers_block = DetailBlock(
            "Watch Providers (via TMDB API / JustWatch)",
            "details_reload.png",
            self,
            action_tooltip="Refresh watch providers",
        )
        self.providers_block.action_button.clicked.connect(self.reload_watch_providers)

        self.watch_provider_refresh_status_label = QLabel(
            "",
            self.providers_block,
        )
        self.watch_provider_refresh_status_label.setObjectName(
            "refreshStatus"
        )
        self.watch_provider_refresh_status_label.setContentsMargins(
            5,
            0,
            0,
            0,
        )
        self.watch_provider_refresh_status_label.hide()
        self.providers_block.add_header_widget(
            self.watch_provider_refresh_status_label
        )

        self._watch_provider_refresh_feedback_timer = QTimer(self)
        self._watch_provider_refresh_feedback_timer.setSingleShot(True)
        self._watch_provider_refresh_feedback_timer.setInterval(
            REFRESH_FEEDBACK_DURATION_MS
        )
        self._watch_provider_refresh_feedback_timer.timeout.connect(
            self._hide_watch_provider_refresh_feedback
        )

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

        self.posters_block = DetailBlock(
            "Posters",
            "details_edit.png",
            self,
            action_tooltip="Edit posters",
        )
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
        lower_block.setFixedHeight(201)

        lower_layout = QVBoxLayout(lower_block)
        lower_layout.setContentsMargins(16, 14, 16, 14)
        lower_layout.setSpacing(8)

        # Smart Fill stays out of the UI until its behavior is implemented.
        # self._add_smart_fill_row(lower_block, lower_layout)

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

    def _add_smart_fill_row(self, lower_block, lower_layout):
        smart_layout = QHBoxLayout()
        smart_layout.setContentsMargins(0, 0, 0, 0)
        smart_layout.setSpacing(8)

        self.smart_input = QLineEdit(lower_block)
        self.smart_input.setFixedHeight(32)
        self.smart_input.setClearButtonEnabled(True)
        self.smart_input.setStyleSheet(INPUT_BOX_STYLE)
        self.smart_input.returnPressed.connect(self.smart_fill)

        self.smart_label = QLabel("Smart Fill:", lower_block)
        smart_layout.addWidget(self.smart_label)
        smart_layout.addWidget(self.smart_input, stretch=1)
        lower_layout.addLayout(smart_layout)

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
        panel_widget.setFixedWidth(MEDIA_STATE_FIELD_WIDTH)

        panel_layout = QVBoxLayout(panel_widget)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(MEDIA_STATE_FIELD_SPACING)

        self.status_combo = self._make_combo(
            panel_widget,
            self._on_status_index_changed,
        )
        self.status_combo.activated.connect(self._on_status_activated)
        self.impression_combo = self._make_combo(panel_widget)
        self.collection_combo = self._make_combo(panel_widget)

        self._add_combo_row(panel_layout, "Status", self.status_combo)
        self._add_combo_row(panel_layout, "Impression", self.impression_combo)
        self._add_combo_row(
            panel_layout,
            COLLECTION_PICK_LABEL,
            self.collection_combo,
        )
        panel_layout.addStretch()

        parent_layout.addWidget(panel_widget, stretch=0)

    def _make_combo(self, parent, change_handler=None):
        combo = DownwardComboBox(parent)
        combo.setMinimumHeight(MEDIA_STATE_COMBO_MIN_HEIGHT)
        combo.setFixedWidth(MEDIA_STATE_FIELD_WIDTH)
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
        self._cancel_active_watch_provider_refresh(reset_state=True)
        self._metadata_refresh_completed_successfully = False
        self._hide_metadata_refresh_feedback()
        self._watch_provider_refresh_completed_successfully = False
        self._hide_watch_provider_refresh_feedback()
        self.media_draft = deepcopy(media_draft)
        self._baseline_media_draft = deepcopy(self.media_draft)
        self._is_dirty = self.media_draft.get("media_id") is None
        self._render_all()
        self._update_action_buttons()

        if self.isVisible():
            QTimer.singleShot(0, self._maybe_auto_refresh_watch_providers)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._maybe_auto_refresh_watch_providers)

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
        if self._is_episode():
            direct_posters = [
                poster
                for poster in posters
                if poster.get("scope", "media") == "media"
            ]
            if direct_posters:
                posters = direct_posters
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

        self.watch_history_layout.addWidget(
            make_icon_button(
                "details_add.png",
                self,
                self.add_watch_history,
                tooltip="Add watch history entry",
            )
        )

        for entry in build_watch_history_display_entries(self.media_draft):
            self.watch_history_layout.addWidget(
                self._make_entry_label(
                    entry["text"],
                    lambda entry=entry: self.edit_watch_history(entry),
                )
            )

        self.watch_history_layout.addStretch()

    def render_notes(self):
        clear_layout(self.notes_layout)

        self.notes_layout.addWidget(
            make_icon_button(
                "details_add.png",
                self,
                self.add_note,
                tooltip="Add note",
            )
        )

        notes = self.media_draft.get("user_data", {}).get("notes", [])

        for note_index in range(len(notes) - 1, -1, -1):
            note = notes[note_index]
            entry = {
                **deepcopy(note),
                "note_index": note_index,
            }
            self.notes_layout.addWidget(
                self._make_note_entry_label(
                    note.get("note") or "",
                    lambda entry=entry: self.edit_note(entry),
                )
            )

        self.notes_layout.addStretch()

    def render_lists(self):
        clear_layout(self.lists_layout)
        self.list_checkboxes = []

        self.lists_layout.addWidget(
            make_icon_button(
                "details_add.png",
                self,
                self.add_list,
                tooltip="Create list",
            )
        )

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

        lists_to_show.sort(
            key=lambda item: (
                (item.get("name") or "").casefold(),
                item.get("name") or "",
                item.get("id") or 0,
            )
        )

        for list_item in lists_to_show:
            checkbox = QCheckBox(self)
            checkbox.setFixedSize(LIST_CHECKBOX_SIZE, LIST_CHECKBOX_SIZE)
            checkbox.setChecked(
                list_item.get("id") in selected_by_id
                or list_item.get("name") in selected_names
            )
            checkbox.setToolTip(
                f"Include this media in {list_item['name']}"
            )
            checkbox.stateChanged.connect(self.mark_dirty)
            self.list_checkboxes.append((checkbox, list_item))
            self.lists_layout.addWidget(
                self._make_list_action_line(checkbox, list_item)
            )

        self.lists_layout.addStretch()

    def _make_entry_label(self, text, callback):
        return ClickableEntryLabel(text, self, callback)

    def _make_note_entry_label(self, text, callback):
        return NotePreviewLabel(text, self, callback)

    def _make_list_action_line(self, checkbox, list_item):
        line = QWidget(self)
        line.setFixedHeight(ENTRY_ACTION_LINE_HEIGHT)
        line.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        line_layout = QHBoxLayout(line)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(0)

        line_layout.addWidget(checkbox, alignment=Qt.AlignmentFlag.AlignVCenter)
        line_layout.addSpacing(LIST_CHECKBOX_TO_TEXT_SPACING)
        label = ClickableEntryLabel(
            list_item.get("name") or "",
            self,
            lambda list_item=deepcopy(list_item): self.edit_list(list_item),
        )
        line_layout.addWidget(
            label,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        return line

    def mark_dirty(self):
        if self._is_populating:
            return

        self._is_dirty = True
        self._update_action_buttons()

    def _on_status_index_changed(self, _index):
        self._status_change_previous_dirty = self._is_dirty
        self._status_change_generation += 1
        self.mark_dirty()

    def _on_status_activated(self, _index):
        previous_status = (
            self.status_combo.take_user_activation_previous_data()
        )
        current_status = self.status_combo.currentData()

        if previous_status == "watched" or current_status != "watched":
            return

        self._schedule_new_watch_entry_dialog(
            previous_status,
            self._status_change_previous_dirty,
        )

    def _schedule_new_watch_entry_dialog(
        self,
        previous_status,
        previous_dirty,
    ):
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
            lambda: (
                self._open_scheduled_watch_entry_dialog(
                    generation,
                    previous_status,
                    previous_dirty,
                )
            ),
        )

    def _open_scheduled_watch_entry_dialog(
        self,
        generation,
        previous_status,
        previous_dirty,
    ):
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

        self._open_watch_entry_details(
            automatic_previous_status=previous_status,
            automatic_previous_dirty=previous_dirty,
            is_automatic=True,
        )

    def _update_action_buttons(self):
        has_media_id = self.media_draft.get("media_id") is not None
        self.delete_button.setEnabled(has_media_id)
        self.save_button.setEnabled(not has_media_id or self._is_dirty)

    def find_media(self):
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

        media_draft = resolve_media_draft_from_query(
            self,
            self.find_media_input.text(),
        )

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
        self._hide_metadata_refresh_feedback()

        if self._metadata_refresh_job_id is not None:
            self.metadata_refresh_manager.cancel(self._metadata_refresh_job_id)

        self._cancel_active_watch_provider_refresh()

    def reload_metadata(self):
        if self._metadata_refresh_in_progress:
            return

        self._metadata_refresh_completed_successfully = False
        self._hide_metadata_refresh_feedback()
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
        self._show_metadata_refresh_feedback(message)

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
        self._metadata_refresh_completed_successfully = True

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

        self._show_metadata_refresh_feedback("Cancelled")

    def _on_metadata_refresh_finished(self, job_id, payload):
        if not self._is_current_metadata_refresh(job_id):
            return

        succeeded = (
            (payload or {}).get("status") == "succeeded"
            and self._metadata_refresh_completed_successfully
        )
        self._metadata_refresh_job_id = None
        self._set_metadata_refresh_busy(False)
        self._metadata_refresh_completed_successfully = False

        if succeeded:
            self._show_metadata_refresh_feedback(
                "Updated",
                auto_hide=True,
            )
        else:
            self._hide_metadata_refresh_feedback()

        QTimer.singleShot(0, self._maybe_auto_refresh_watch_providers)

    def _is_current_metadata_refresh(self, job_id):
        return job_id == self._metadata_refresh_job_id

    def _set_metadata_refresh_busy(self, is_busy, message=None):
        self._metadata_refresh_in_progress = is_busy
        self._update_refresh_action_buttons()
        self.posters_block.action_button.setEnabled(not is_busy)
        self.find_media_input.setEnabled(not is_busy)
        self.lower_block.setEnabled(not is_busy)

        if is_busy:
            self._show_metadata_refresh_feedback(
                message or "Refreshing metadata…"
            )
            self.save_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return

        self._update_action_buttons()

    def _show_metadata_refresh_feedback(self, message, *, auto_hide=False):
        self._metadata_refresh_feedback_timer.stop()
        self.metadata_refresh_status_label.setText(message)
        self.metadata_refresh_status_label.show()

        if auto_hide:
            self._metadata_refresh_feedback_timer.start()

    def _hide_metadata_refresh_feedback(self):
        self._metadata_refresh_feedback_timer.stop()
        self.metadata_refresh_status_label.hide()
        self.metadata_refresh_status_label.clear()

    def _update_refresh_action_buttons(self):
        self.metadata_block.action_button.setEnabled(
            not self._metadata_refresh_in_progress
        )
        self.providers_block.action_button.setEnabled(
            not (
                self._metadata_refresh_in_progress
                or self._watch_provider_refresh_in_progress
            )
        )

    def _maybe_auto_refresh_watch_providers(self):
        if (
            not self._auto_refresh_watch_providers
            or self._is_closing
            or self._metadata_refresh_in_progress
            or self._watch_provider_refresh_in_progress
        ):
            return

        media_id = self.media_draft.get("media_id")

        if (
            media_id is None
            or media_id in self._auto_refreshed_watch_provider_media_ids
        ):
            return

        match = build_tmdb_match_from_metadata(
            self.media_draft.get("metadata") or {}
        )

        try:
            job_id = self.watch_provider_refresh_manager.start_refresh(
                media_id,
                match,
            )
        except Exception:
            return

        self._watch_provider_refresh_job_id = job_id
        self._watch_provider_refresh_target_media_id = media_id
        self._watch_provider_refresh_is_manual = False
        self._watch_provider_refresh_completed_successfully = False
        self._hide_watch_provider_refresh_feedback()
        self._auto_refreshed_watch_provider_media_ids.add(media_id)
        self._set_watch_provider_refresh_busy(True)

    def _on_watch_provider_refresh_succeeded(self, job_id, payload):
        if (
            not self._is_current_watch_provider_refresh(job_id)
            or self._is_closing
        ):
            return

        payload = payload or {}
        media_id = payload.get("media_id")

        if (
            media_id != self._watch_provider_refresh_target_media_id
            or media_id != self.media_draft.get("media_id")
            or "watch_providers" not in payload
            or not payload.get("checked_at")
        ):
            self._discard_current_auto_provider_refresh()

            if self._watch_provider_refresh_is_manual:
                QMessageBox.warning(
                    self,
                    "Watch Providers",
                    "Watch-provider refresh returned incomplete data.",
                )

            return

        providers = deepcopy(payload["watch_providers"] or [])
        checked_at = payload["checked_at"]

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
                self._discard_current_auto_provider_refresh()

                if self._watch_provider_refresh_is_manual:
                    QMessageBox.warning(
                        self,
                        "Watch Providers",
                        str(exc),
                    )

                return

            self._apply_watch_provider_refresh(providers, checked_at)
            self.result_payload["database_changed"] = True
        else:
            self._apply_new_watch_provider_refresh(providers, checked_at)

        self._watch_provider_refresh_completed_successfully = True

    def _on_watch_provider_refresh_failed(self, job_id, payload):
        if not self._is_current_watch_provider_refresh(job_id):
            return

        self._discard_current_auto_provider_refresh()

        if self._watch_provider_refresh_is_manual and not self._is_closing:
            QMessageBox.warning(
                self,
                "Watch Providers",
                (payload or {}).get("message")
                or "Watch-provider refresh failed.",
            )

    def _on_watch_provider_refresh_cancelled(self, job_id, payload):
        del payload

        if not self._is_current_watch_provider_refresh(job_id):
            return

        self._discard_current_auto_provider_refresh()

    def _on_watch_provider_refresh_finished(self, job_id, payload):
        if not self._is_current_watch_provider_refresh(job_id):
            return

        was_manual = self._watch_provider_refresh_is_manual
        succeeded = (
            (payload or {}).get("status") == "succeeded"
            and self._watch_provider_refresh_completed_successfully
        )
        self._watch_provider_refresh_job_id = None
        self._watch_provider_refresh_target_media_id = None
        self._watch_provider_refresh_is_manual = False
        self._watch_provider_refresh_completed_successfully = False
        self._set_watch_provider_refresh_busy(False)

        if was_manual and succeeded:
            self._show_watch_provider_refresh_feedback(
                "Updated",
                auto_hide=True,
            )
        else:
            self._hide_watch_provider_refresh_feedback()

    def _is_current_watch_provider_refresh(self, job_id):
        return job_id == self._watch_provider_refresh_job_id

    def _set_watch_provider_refresh_busy(self, is_busy):
        self._watch_provider_refresh_in_progress = is_busy
        self._update_refresh_action_buttons()

    def _show_watch_provider_refresh_feedback(
        self,
        message,
        *,
        auto_hide=False,
    ):
        self._watch_provider_refresh_feedback_timer.stop()
        self.watch_provider_refresh_status_label.setText(message)
        self.watch_provider_refresh_status_label.show()

        if auto_hide:
            self._watch_provider_refresh_feedback_timer.start()

    def _hide_watch_provider_refresh_feedback(self):
        self._watch_provider_refresh_feedback_timer.stop()
        self.watch_provider_refresh_status_label.hide()
        self.watch_provider_refresh_status_label.clear()

    def _cancel_active_watch_provider_refresh(self, reset_state=False):
        self._hide_watch_provider_refresh_feedback()

        if self._watch_provider_refresh_job_id is not None:
            self.watch_provider_refresh_manager.cancel(
                self._watch_provider_refresh_job_id
            )

        if not reset_state:
            return

        self._discard_current_auto_provider_refresh()
        self._watch_provider_refresh_job_id = None
        self._watch_provider_refresh_target_media_id = None
        self._watch_provider_refresh_is_manual = False
        self._watch_provider_refresh_completed_successfully = False
        self._set_watch_provider_refresh_busy(False)

    def _discard_current_auto_provider_refresh(self):
        if (
            not self._watch_provider_refresh_is_manual
            and self._watch_provider_refresh_target_media_id is not None
        ):
            self._auto_refreshed_watch_provider_media_ids.discard(
                self._watch_provider_refresh_target_media_id
            )

    def _apply_watch_provider_refresh(self, providers, checked_at):
        was_dirty = self._is_dirty
        metadata = self.media_draft.setdefault("metadata", {})
        metadata["last_tmdb_watch_providers_checked_at"] = checked_at
        self.media_draft["watch_providers"] = deepcopy(providers)

        baseline_metadata = self._baseline_media_draft.setdefault(
            "metadata",
            {},
        )
        baseline_metadata["last_tmdb_watch_providers_checked_at"] = checked_at
        self._baseline_media_draft["watch_providers"] = deepcopy(providers)
        self._is_dirty = was_dirty
        self.render_watch_providers()
        self._update_action_buttons()

    def _apply_new_watch_provider_refresh(self, providers, checked_at):
        metadata = self.media_draft.setdefault("metadata", {})
        metadata["last_tmdb_watch_providers_checked_at"] = checked_at
        self.media_draft["watch_providers"] = deepcopy(providers)
        self._is_dirty = True
        self.render_watch_providers()
        self._update_action_buttons()

    def reload_watch_providers(self):
        if (
            self._metadata_refresh_in_progress
            or self._watch_provider_refresh_in_progress
        ):
            return

        media_id = self.media_draft.get("media_id")
        match = build_tmdb_match_from_metadata(
            self.media_draft.get("metadata") or {}
        )
        self._watch_provider_refresh_completed_successfully = False
        self._hide_watch_provider_refresh_feedback()

        try:
            job_id = self.watch_provider_refresh_manager.start_refresh(
                media_id,
                match,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Watch Providers", str(exc))
            return

        self._watch_provider_refresh_job_id = job_id
        self._watch_provider_refresh_target_media_id = media_id
        self._watch_provider_refresh_is_manual = True
        self._set_watch_provider_refresh_busy(True)
        self._show_watch_provider_refresh_feedback(
            "Fetching providers…"
        )

    def edit_posters(self):
        dialog = ManagePostersDialog(self, self.media_draft)

        if dialog.exec() != QDialog.Accepted:
            return

        self.media_draft["posters"] = deepcopy(
            dialog.result_payload.get("posters", [])
        )
        self.media_draft[POSTER_MANAGEMENT_KEY] = deepcopy(
            dialog.result_payload.get("management_state") or {}
        )
        self.mark_dirty()
        self.render_posters()

    def smart_fill(self):
        print("Smart Fill clicked")

    def edit_watch_history(self, entry=None):
        self._open_watch_entry_details(entry)

    def add_watch_history(self):
        self._open_watch_entry_details()

    def _open_watch_entry_details(
        self,
        entry=None,
        *,
        automatic_previous_status=None,
        automatic_previous_dirty=None,
        is_automatic=False,
    ):
        if self._watch_entry_dialog_active:
            return

        self._watch_entry_dialog_active = True

        try:
            dialog = WatchEntryDetailsDialog(self, self.media_draft, entry)
            result = dialog.exec()
        finally:
            self._watch_entry_dialog_active = False

        if result != QDialog.Accepted:
            if is_automatic:
                self._restore_status_after_automatic_entry_cancel(
                    automatic_previous_status,
                    automatic_previous_dirty,
                )
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

    def _restore_status_after_automatic_entry_cancel(
        self,
        previous_status,
        previous_dirty,
    ):
        metadata = self.media_draft.get("metadata") or {}

        if metadata.get("media_type") not in {"movie", "episode"}:
            return

        user_data = self.media_draft.get("user_data") or {}

        if user_data.get("watch_history"):
            return

        set_combo_value(self.status_combo, previous_status)
        self.status_combo.reset_user_activation_baseline()
        self._is_dirty = previous_dirty
        self._update_action_buttons()

    def edit_note(self, entry=None):
        dialog = NoteDetailsDialog(self, entry)

        if dialog.exec() != QDialog.Accepted:
            return

        apply_note_result(
            self.media_draft,
            entry,
            dialog.result_payload,
        )
        self.mark_dirty()
        self.render_notes()

    def add_note(self):
        self.edit_note()

    def edit_list(self, list_item=None):
        dialog = ListDetailsDialog(
            self,
            list_item,
            existing_lists=self.all_lists,
        )

        if dialog.exec() != QDialog.Accepted:
            return

        self._apply_list_checkboxes_to_draft()
        action = dialog.result_payload.get("action")

        try:
            with get_connection() as conn:
                if action == "delete":
                    list_id = list_item.get("id")

                    if not media_repo.delete_list(conn, list_id):
                        raise ValueError(f"lists id {list_id} does not exist.")

                    saved_list = None
                elif action == "save" and list_item is None:
                    saved_list = media_repo.create_list(
                        conn,
                        dialog.result_payload.get("name"),
                        dialog.result_payload.get("description"),
                    )
                elif action == "save":
                    saved_list = media_repo.update_list(
                        conn,
                        list_item.get("id"),
                        dialog.result_payload.get("name"),
                        dialog.result_payload.get("description"),
                    )
                else:
                    raise ValueError(f"Unsupported list action: {action}")
        except Exception as exc:
            QMessageBox.warning(self, "List Details", str(exc))
            return

        if action == "delete":
            self._remove_list_references(list_item.get("id"))
        elif list_item is not None:
            self._rename_list_references(saved_list)

        self._load_all_lists()
        self.render_lists()

    def add_list(self):
        self.edit_list()

    def _apply_list_checkboxes_to_draft(self):
        user_data = self.media_draft.setdefault("user_data", {})
        user_data["lists"] = self._collect_selected_lists(
            user_data.get("lists", [])
        )

    def _rename_list_references(self, saved_list):
        list_id = saved_list.get("id")

        for draft in (self.media_draft, self._baseline_media_draft):
            user_data = draft.setdefault("user_data", {})

            for list_reference in user_data.get("lists", []):
                if list_reference.get("id") == list_id:
                    list_reference["name"] = saved_list.get("name")

    def _remove_list_references(self, list_id):
        for draft in (self.media_draft, self._baseline_media_draft):
            user_data = draft.setdefault("user_data", {})
            user_data["lists"] = [
                list_reference
                for list_reference in user_data.get("lists", [])
                if list_reference.get("id") != list_id
            ]

    def save_media(self):
        if self._metadata_refresh_in_progress:
            return

        self._apply_form_to_draft()
        media_id = self.media_draft.get("media_id")

        save_result = None

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
                    save_result = draft_saver.save_existing_media_changes(
                        conn,
                        self._baseline_media_draft,
                        self.media_draft,
                    )

                apply_inserted_ids_to_draft(self.media_draft, save_result)
        except Exception as exc:
            if save_result is not None:
                poster_storage.cleanup_created_poster_files(
                    save_result.get("poster_files_created", [])
                )
            QMessageBox.warning(self, "Save Media", str(exc))
            return

        files_to_delete = save_result.get("poster_files_to_delete", [])
        if files_to_delete:
            try:
                with get_connection() as conn:
                    poster_storage.delete_unreferenced_poster_files(
                        conn,
                        files_to_delete,
                    )
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Save Media",
                    f"Media was saved, but an old poster file could not be removed: {exc}",
                )

        poster_storage.finalize_managed_poster_draft(self.media_draft)

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

            QLabel#refreshStatus {
                font-style: italic;
            }

            QFrame#detailBlock {
                background-color: #f1f1f1;
                border: 1px solid #555555;
            }

            QLineEdit,
            QPlainTextEdit {
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

        """ + MEDIA_STATE_COMBO_STYLE + """
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


def load_poster_pixmap(poster):
    import_path = poster.get("_import_path")

    if import_path:
        pixmap = QPixmap(str(import_path))
        return pixmap if not pixmap.isNull() else None

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

    image_url = tmdb.build_tmdb_image_url(
        normalized_filename,
        size=TMDB_POSTER_PREVIEW_SIZE,
    )

    if image_url is None:
        return None

    try:
        response = requests.get(image_url, timeout=8)
        response.raise_for_status()
    except requests.RequestException:
        return None

    pixmap = QPixmap()

    if not pixmap.loadFromData(response.content):
        return None

    return pixmap
