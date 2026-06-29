from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import requests

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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
from app.media_details_formatters import (
    WATCH_PROVIDER_GROUPS,
    build_metadata_display_rows,
    build_tmdb_match_from_metadata,
    build_watch_history_display_lines,
    format_watch_provider_checked_at,
    get_poster_curation_status,
    group_watch_providers,
)
from app.media_lookup import resolve_media_draft_from_query
from db.connection import get_connection


DETAIL_ICON_DIR = Path("app/assets/details_dialog_icons")
POSTER_DIR = Path("data/media_posters")
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
TMDB_POSTER_PREVIEW_SIZE = "w185"
POSTER_PREVIEW_HEIGHT = 232
# Tweak this value to fine-tune vertical spacing in open dropdown menus.
COMBO_POPUP_ITEM_HEIGHT = 28

STATUS_OPTIONS = (
    ("to_watch", "To Watch"),
    ("watched", "Watched"),
    ("watching", "Watching"),
    ("not_interested", "Not Interested"),
    ("dropped", "Dropped"),
)

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
        header_layout.setSpacing(4)

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
    def showPopup(self):
        super().showPopup()

        popup = self.view().window()

        if popup is not None:
            popup.move(self.mapToGlobal(QPoint(0, self.height())))


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


class MediaDetailsDialog(QDialog):
    def __init__(self, parent, media_draft, input_query=None):
        super().__init__(parent)

        self.media_draft = deepcopy(media_draft)
        self.result_payload = {"status": "cancelled"}
        self.all_lists = []
        self.list_checkboxes = []
        self._is_dirty = False
        self._is_populating = False

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

        self.search_button = QPushButton("Search Media", self)
        self.search_button.setMinimumHeight(32)
        self.search_button.setFixedWidth(115)
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

        lower_block = self._build_lower_block()
        footer_layout = self._build_footer()

        main_layout.addLayout(search_layout)
        main_layout.addLayout(upper_layout, stretch=1)
        main_layout.addWidget(lower_block)
        main_layout.addLayout(footer_layout)

    def _build_metadata_block(self):
        block = DetailBlock("Metadata", "reload.png", self)
        block.action_button.clicked.connect(self.reload_metadata)

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

        self.providers_block = DetailBlock("Watch Providers", "reload.png", self)
        self.providers_block.action_button.clicked.connect(self.reload_watch_providers)
        self.providers_layout = QVBoxLayout()
        self.providers_layout.setContentsMargins(0, 0, 0, 0)
        self.providers_layout.setSpacing(4)
        self.providers_block.body_layout.addLayout(self.providers_layout)

        self.posters_block = DetailBlock("Posters", "edit.png", self)
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
        self.smart_button.setFixedWidth(115)
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
            button.setFixedWidth(115)
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

        self.status_combo = self._make_combo(panel_widget)
        self.impression_combo = self._make_combo(panel_widget)
        self.collection_combo = self._make_combo(panel_widget)

        self._add_combo_row(panel_layout, "Status", self.status_combo)
        self._add_combo_row(panel_layout, "Impression", self.impression_combo)
        self._add_combo_row(panel_layout, "Collection Pick", self.collection_combo)
        panel_layout.addStretch()

        parent_layout.addWidget(panel_widget, stretch=0)

    def _make_combo(self, parent):
        combo = DownwardComboBox(parent)
        combo.setMinimumHeight(30)
        combo.setFixedWidth(190)
        view = ComboPopupView(combo)
        view.setItemDelegate(ComboPopupItemDelegate(combo, view))
        combo.setView(view)
        combo.currentIndexChanged.connect(self.mark_dirty)
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
            provider_label = QLabel(f"{label}: {value}", self.providers_block)
            provider_label.setWordWrap(False)
            provider_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.providers_layout.addWidget(provider_label)

        checked_at = format_watch_provider_checked_at(
            self.media_draft.get("watch_providers", [])
        )
        checked_at_label = QLabel(
            f"Checked at: {checked_at or 'None'}",
            self.providers_block,
        )
        checked_at_label.setWordWrap(False)
        checked_at_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.providers_layout.addWidget(checked_at_label)

        self.providers_layout.addStretch()

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
        populate_status_combo(self.status_combo, user_data.get("watch_state"))
        populate_combo(self.impression_combo, IMPRESSION_OPTIONS, user_data.get("impression"))
        populate_combo(
            self.collection_combo,
            COLLECTION_PICK_OPTIONS,
            user_data.get("is_collection_pick"),
        )

    def render_watch_history(self):
        clear_layout(self.watch_history_layout)

        for line in build_watch_history_display_lines(self.media_draft):
            self.watch_history_layout.addLayout(
                self._make_action_line("edit.png", line, self.edit_watch_history)
            )

        self.watch_history_layout.addWidget(
            make_icon_button("add.png", self, self.add_watch_history)
        )
        self.watch_history_layout.addStretch()

    def render_notes(self):
        clear_layout(self.notes_layout)

        for note in self.media_draft.get("user_data", {}).get("notes", []):
            self.notes_layout.addLayout(
                self._make_action_line(
                    "edit.png",
                    note.get("user_note") or "",
                    self.edit_note,
                )
            )

        self.notes_layout.addWidget(make_icon_button("add.png", self, self.add_note))
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

        self.lists_layout.addWidget(make_icon_button("add.png", self, self.add_list))
        self.lists_layout.addStretch()

    def _make_action_line(self, icon_name, text, callback):
        line_layout = QHBoxLayout()
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(8)

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

    def _update_action_buttons(self):
        has_media_id = self.media_draft.get("media_id") is not None
        self.delete_button.setEnabled(has_media_id)
        self.save_button.setEnabled(not has_media_id or self._is_dirty)

    def search_media(self):
        if self._is_dirty:
            result = QMessageBox.question(
                self,
                "Discard changes?",
                "Search Media will replace the current draft and discard unsaved changes.",
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

    def reload_metadata(self):
        print("Metadata reload clicked")

    def reload_watch_providers(self):
        try:
            providers = tmdb_fetcher.get_tmdb_media_watch_providers(
                build_tmdb_match_from_metadata(self.media_draft.get("metadata") or {})
            )
        except Exception as exc:
            QMessageBox.warning(self, "Watch Providers", str(exc))
            return

        self.media_draft["watch_providers"] = providers
        media_id = self.media_draft.get("media_id")

        if media_id is not None:
            try:
                with get_connection() as conn:
                    media_repo.replace_media_watch_providers(conn, media_id, providers)
            except Exception as exc:
                QMessageBox.warning(self, "Watch Providers", str(exc))
                return
        else:
            self._is_dirty = True

        self.render_watch_providers()
        self._update_action_buttons()

    def edit_posters(self):
        print("Poster edit clicked")

    def smart_fill(self):
        print("Smart Fill clicked")

    def edit_watch_history(self):
        print("Watch history edit clicked")

    def add_watch_history(self):
        print("Watch history add clicked")

    def edit_note(self):
        print("Note edit clicked")

    def add_note(self):
        print("Note add clicked")

    def add_list(self):
        print("List add clicked")

    def save_media(self):
        self._apply_form_to_draft()

        try:
            with get_connection() as conn:
                save_result = draft_saver.save_media_draft_with_posters(
                    conn,
                    self.media_draft,
                )
        except Exception as exc:
            QMessageBox.warning(self, "Save Media", str(exc))
            return

        self.result_payload = {
            "status": "saved",
            "media_id": save_result["media_id"],
            "media_draft": self.media_draft,
            "save_result": save_result,
        }
        self.accept()

    def delete_media(self):
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
        user_data["impression"] = self.impression_combo.currentData()
        user_data["is_collection_pick"] = self.collection_combo.currentData()
        user_data["lists"] = self._collect_selected_lists(user_data.get("lists", []))
        self.media_draft["user_data"] = user_data

    def _collect_selected_lists(self, current_lists):
        current_by_id = {
            item.get("id"): item
            for item in current_lists
            if item.get("id") is not None
        }
        current_by_name = {
            item.get("name"): item
            for item in current_lists
            if item.get("name")
        }
        selected_lists = []

        for checkbox, list_item in self.list_checkboxes:
            if not checkbox.isChecked():
                continue

            current = (
                current_by_id.get(list_item.get("id"))
                or current_by_name.get(list_item.get("name"))
                or {}
            )
            selected_lists.append({
                "id": list_item.get("id"),
                "name": list_item.get("name"),
                "entry_note": current.get("entry_note"),
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
                image: url(app/assets/details_dialog_icons/dropdown_arrow.svg);
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
    button.setFixedSize(22, 22)
    button.setIcon(QIcon(str(DETAIL_ICON_DIR / icon_name)))
    button.setIconSize(QSize(18, 18))
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


def populate_status_combo(combo, current_value):
    combo.blockSignals(True)
    combo.clear()

    if current_value == "suggested":
        combo.addItem("Suggested (system)", "suggested")
        item = combo.model().item(0)
        if item is not None:
            item.setEnabled(False)

    for value, label in STATUS_OPTIONS:
        combo.addItem(label, value)

    set_combo_value(combo, current_value)
    combo.blockSignals(False)


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
