from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.media_state_controls import (
    COLLECTION_PICK_OPTIONS,
    IMPRESSION_OPTIONS,
    ClickableEntryLabel,
    ComboPopupItemDelegate,
    ComboPopupView,
    DownwardComboBox,
    populate_combo,
    set_combo_value,
)


POSTER_WIDTH = 180
PLACEHOLDER_POSTER_HEIGHT = 270
DATE_COLUMN_WIDTH = 230
POSTER_DIR = Path(__file__).resolve().parents[1] / "data" / "media_posters"


class HistoryEntryWidget(QWidget):
    details_requested = Signal(int)
    state_change_requested = Signal(int, str, object, object)

    def __init__(self, entry, parent=None):
        super().__init__(parent)

        self.entry = entry
        self.state_media_id = entry.state_media_id
        self._confirmed_state = {
            "impression": entry.impression,
            "is_collection_pick": entry.is_collection_pick,
        }

        self.setObjectName("historyEntry")
        self._build_ui()
        self.set_state_values(
            entry.impression,
            entry.is_collection_pick,
            confirmed=True,
        )

    @property
    def confirmed_state(self):
        return dict(self._confirmed_state)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.date_label = QLabel(self.entry.formatted_date, self)
        self.date_label.setObjectName("historyDate")
        self.date_label.setFixedWidth(DATE_COLUMN_WIDTH)
        self.date_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        date_font = self.date_label.font()
        date_font.setBold(True)
        date_font.setPointSize(max(date_font.pointSize(), 14))
        self.date_label.setFont(date_font)

        self.poster_label = QLabel(self)
        self.poster_label.setObjectName("historyPoster")
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._render_poster()

        details_widget = QWidget(self)
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(10)

        self.title_label = ClickableEntryLabel(
            self.entry.title,
            details_widget,
        )
        self.title_label.setObjectName("historyTitle")
        self.title_label.setFixedHeight(30)
        title_font = self.title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(max(title_font.pointSize(), 16))
        self.title_label.setFont(title_font)
        self.title_label.activated.connect(
            lambda: self.details_requested.emit(self.entry.details_media_id)
        )

        self.impression_combo = self._make_combo(details_widget, width=280)
        self.collection_combo = self._make_combo(details_widget, width=150)

        impression_row = self._make_combo_row(
            "Impression:",
            self.impression_combo,
            details_widget,
        )
        collection_row = self._make_combo_row(
            "Collection Pick:",
            self.collection_combo,
            details_widget,
        )

        details_layout.addWidget(self.title_label)
        details_layout.addLayout(impression_row)
        details_layout.addLayout(collection_row)
        details_layout.addStretch()

        layout.addWidget(self.date_label)
        layout.addWidget(self.poster_label)
        layout.addWidget(details_widget, 1)

        self.impression_combo.activated.connect(
            lambda _index: self._request_state_change("impression")
        )
        self.collection_combo.activated.connect(
            lambda _index: self._request_state_change(
                "is_collection_pick"
            )
        )

    def _make_combo(self, parent, *, width):
        combo = DownwardComboBox(parent)
        combo.setFixedWidth(width)
        combo.setMinimumHeight(30)
        view = ComboPopupView(combo)
        view.setItemDelegate(ComboPopupItemDelegate(combo, view))
        combo.setView(view)
        return combo

    def _make_combo_row(self, label_text, combo, parent):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        label = QLabel(label_text, parent)
        label_font = QFont(label.font())
        label_font.setPointSize(max(label_font.pointSize(), 13))
        label.setFont(label_font)

        row.addWidget(label)
        row.addWidget(combo)
        row.addStretch()
        return row

    def _render_poster(self):
        poster = self.entry.poster or {}
        filename = str(poster.get("filename") or "").lstrip("/")
        pixmap = QPixmap(str(POSTER_DIR / filename)) if filename else QPixmap()

        if pixmap.isNull():
            self.poster_label.setFixedSize(
                POSTER_WIDTH,
                PLACEHOLDER_POSTER_HEIGHT,
            )
            self.poster_label.setText("No poster")
            self.poster_label.setStyleSheet(
                "background-color: #dedede;"
                "border: 1px solid #c6c6c6;"
                "color: #777777;"
            )
            return

        scaled = pixmap.scaledToWidth(
            POSTER_WIDTH,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.poster_label.setFixedSize(scaled.size())
        self.poster_label.setPixmap(scaled)
        self.poster_label.setStyleSheet("background-color: #dedede;")

    def _request_state_change(self, field):
        combo = (
            self.impression_combo
            if field == "impression"
            else self.collection_combo
        )
        expected_value = self._confirmed_state[field]
        desired_value = combo.currentData()

        if desired_value == expected_value:
            return

        self.state_change_requested.emit(
            self.state_media_id,
            field,
            expected_value,
            desired_value,
        )

    def set_state_values(
        self,
        impression,
        is_collection_pick,
        *,
        confirmed,
    ):
        self.impression_combo.blockSignals(True)
        self.collection_combo.blockSignals(True)

        if self.impression_combo.count() == 0:
            populate_combo(
                self.impression_combo,
                IMPRESSION_OPTIONS,
                impression,
            )
        else:
            set_combo_value(self.impression_combo, impression)

        if self.collection_combo.count() == 0:
            populate_combo(
                self.collection_combo,
                COLLECTION_PICK_OPTIONS,
                is_collection_pick,
            )
        else:
            set_combo_value(self.collection_combo, is_collection_pick)

        self.impression_combo.blockSignals(False)
        self.collection_combo.blockSignals(False)

        if confirmed:
            self._confirmed_state = {
                "impression": impression,
                "is_collection_pick": is_collection_pick,
            }
            self.impression_combo.reset_user_activation_baseline()
            self.collection_combo.reset_user_activation_baseline()

    def set_editing_enabled(self, enabled):
        self.impression_combo.setEnabled(enabled)
        self.collection_combo.setEnabled(enabled)
