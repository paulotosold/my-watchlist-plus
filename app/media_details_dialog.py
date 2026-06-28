from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def open_media_details_dialog(parent, media_draft, input_query=None):
    dialog = MediaDetailsDialog(
        parent=parent,
        media_draft=media_draft,
        input_query=input_query,
    )

    if dialog.exec() == QDialog.Accepted:
        return dialog.confirmed_draft

    return None


class MediaDetailsDialog(QDialog):
    def __init__(self, parent, media_draft, input_query=None):
        super().__init__(parent)

        self.media_draft = media_draft
        self.confirmed_draft = None

        self.setWindowTitle("Media Details")
        self.setFixedSize(1180, 760)

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Original input")
        self.input_line.setText(input_query or "")
        self.input_line.setReadOnly(False)

        self.update_form_button = QPushButton("Update Form")

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_line, stretch=1)
        input_row.addWidget(self.update_form_button)

        self.metadata_panel = MediaMetadata(media_draft=media_draft)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(input_row)
        main_layout.addWidget(self.metadata_panel, stretch=1)


class MediaMetadata(QGroupBox):
    def __init__(self, media_draft: dict):
        super().__init__()

        self.media_draft = media_draft
        self.metadata = media_draft.get("metadata") or {}
        self.series_view = media_draft.get("series_view") or {}

        self.refresh_button = QPushButton("⟳")
        self.refresh_button.setFixedWidth(34)
        self.refresh_button.clicked.connect(self.refresh_metadata)

        title_label = QLabel("Metadata:")
        title_label.setStyleSheet("font-weight: bold;")

        header_layout = QHBoxLayout()
        header_layout.addWidget(self.refresh_button)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.content_widget = QWidget()
        self.content_layout = QGridLayout(self.content_widget)
        self.content_layout.setColumnStretch(1, 1)
        self.content_layout.setVerticalSpacing(8)
        self.content_layout.setHorizontalSpacing(12)

        self.scroll_area.setWidget(self.content_widget)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(header_layout)
        main_layout.addWidget(self.scroll_area)

        self.render_metadata()

    def refresh_metadata(self):
        print("Refresh metadata clicked")

    def render_metadata(self):
        clear_layout(self.content_layout)

        row_index = 0

        for label, value in iter_metadata_rows(self.metadata, self.series_view):
            if is_empty_metadata_value(value):
                continue

            label_widget = QLabel(f"{label}:")
            label_widget.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            label_widget.setMinimumWidth(150)

            value_widget = QLabel(format_metadata_value(value))
            value_widget.setWordWrap(True)
            value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_widget.setAlignment(Qt.AlignTop | Qt.AlignLeft)

            self.content_layout.addWidget(label_widget, row_index, 0)
            self.content_layout.addWidget(value_widget, row_index, 1)

            row_index += 1

        self.content_layout.setRowStretch(row_index, 1)

def iter_metadata_rows(metadata: dict, series_view: dict | None = None):
    media_type = metadata.get("media_type")

    yield "TMDB ID", metadata.get("tmdb_id")
    yield "IMDb ID", metadata.get("imdb_id")
    yield "Type", format_media_type(media_type)

    if media_type == "episode":
        episode_details = metadata.get("episode_details") or {}
        yield "Series", episode_details.get("series_title")

    yield "Title", metadata.get("title")
    yield "Original Title", metadata.get("original_title")

    if media_type == "episode":
        episode_details = metadata.get("episode_details") or {}
        yield "Episode", episode_details.get("episode_num")
        yield "Season", episode_details.get("season_num")

    yield "Production Status", metadata.get("production_status")

    if media_type == "series":
        series_summary = (series_view or {}).get("summary") or {}
        yield "First Air Date", series_summary.get("first_air_date")
        yield "Last Air Date", series_summary.get("last_air_date")
        yield "Seasons", series_summary.get("season_count")
        yield "Episodes", series_summary.get("episode_count")
        yield "Total Runtime", series_summary.get("total_runtime_min")
    else:
        yield "Release Date", metadata.get("release_date")
        yield "Runtime", metadata.get("runtime_min")

    yield "Genres", metadata.get("genres")
    yield "Spoken Languages", metadata.get("spoken_languages")
    yield "Origin Language", metadata.get("origin_language")
    yield "Production Countries", metadata.get("production_countries")
    yield "Production Companies", metadata.get("production_companies")

    if media_type == "series":
        yield "Created by", metadata.get("creators")
    else:
        yield "Directed by", metadata.get("directors")

    yield "Writers", metadata.get("writers")
    yield "Main Cast", metadata.get("actors")


def format_metadata_value(value: Any) -> str:
    if value is None:
        return "None"

    if isinstance(value, list):
        return format_list_value(value)

    if isinstance(value, dict):
        return format_dict_value(value)

    return str(value)


def format_list_value(items: list) -> str:
    if not items:
        return "None"

    formatted_items = []

    for item in items:
        if isinstance(item, dict):
            formatted_items.append(format_dict_item(item))
        else:
            formatted_items.append(str(item))

    return ", ".join(formatted_items)


def format_dict_item(item: dict) -> str:
    if "name" in item:
        name = item["name"]

        if item.get("job"):
            return f"{name} ({item['job']})"

        if item.get("character"):
            return f"{name} as {item['character']}"

        return str(name)

    return format_dict_value(item)


def format_dict_value(item: dict) -> str:
    parts = []

    for key, value in item.items():
        if is_empty_metadata_value(value):
            continue

        label = key.replace("_", " ").title()
        parts.append(f"{label}: {value}")

    return ", ".join(parts)


def format_media_type(media_type: str | None) -> str:
    if media_type is None:
        return "None"

    return media_type.capitalize()


def is_empty_metadata_value(value: Any) -> bool:
    return value is None or value == [] or value == {}


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)

        widget = item.widget()

        if widget is not None:
            widget.deleteLater()
