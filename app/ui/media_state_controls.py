from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QListView,
    QStyle,
    QStyledItemDelegate,
)

from app.media_user_data.watch_states import VALID_WATCH_STATES_BY_MEDIA_TYPE
from app.paths import ASSETS_DIR


COMBO_POPUP_ITEM_HEIGHT = 28
MEDIA_STATE_FIELD_WIDTH = 190
MEDIA_STATE_FIELD_SPACING = 4
MEDIA_STATE_COMBO_MIN_HEIGHT = 30

_DROPDOWN_ARROW_PATH = (ASSETS_DIR / "dropdown_arrow.svg").as_posix()

MEDIA_STATE_COMBO_STYLE = """
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
    image: url("%s");
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
""" % _DROPDOWN_ARROW_PATH

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
NONE_WATCH_STATE_LABEL = "None"
NO_WATCH_STATE_LABELS = {
    media_type: NONE_WATCH_STATE_LABEL
    for media_type in VALID_WATCH_STATES_BY_MEDIA_TYPE
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
        ((None, NONE_WATCH_STATE_LABEL),),
    )
    populate_combo(combo, options, current_value)


def set_combo_value(combo, value):
    index = combo.findData(value)

    if index >= 0:
        combo.setCurrentIndex(index)
        return

    if combo.count():
        combo.setCurrentIndex(0)
