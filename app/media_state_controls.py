from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QListView,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
)

from app.watch_states import VALID_WATCH_STATES_BY_MEDIA_TYPE


CLICKABLE_ENTRY_LABEL_HEIGHT = 20
COMBO_POPUP_ITEM_HEIGHT = 28
MEDIA_STATE_FIELD_WIDTH = 190
MEDIA_STATE_FIELD_SPACING = 4
MEDIA_STATE_COMBO_MIN_HEIGHT = 30

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
"""

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


class ClickableEntryLabel(QLabel):
    activated = Signal()

    def __init__(self, text, parent=None, callback=None):
        super().__init__(text or "", parent)

        self._press_position = None
        self._press_started_over_text = False
        self._pointer_over_text = False
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.setWordWrap(False)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setFixedHeight(CLICKABLE_ENTRY_LABEL_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumWidth(0)

        if callback is not None:
            self.activated.connect(callback)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._update_pointer_state(event.position().toPoint())

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_pointer_over_text(False)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._update_pointer_state(event.position().toPoint())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
            self._press_started_over_text = self._is_over_rendered_text(
                self._press_position
            )

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        release_position = event.position().toPoint()
        should_activate = (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_position is not None
            and self._press_started_over_text
            and self._is_over_rendered_text(release_position)
            and (
                release_position - self._press_position
            ).manhattanLength() < QApplication.startDragDistance()
        )

        super().mouseReleaseEvent(event)
        self._press_position = None
        self._press_started_over_text = False

        if should_activate and not self.hasSelectedText():
            self.activated.emit()

    def keyPressEvent(self, event):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            event.accept()
            self.activated.emit()
            return

        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._refresh_underline()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._refresh_underline()

    def _update_pointer_state(self, position):
        self._set_pointer_over_text(self._is_over_rendered_text(position))

    def _set_pointer_over_text(self, is_over_text):
        if self._pointer_over_text == is_over_text:
            return

        self._pointer_over_text = is_over_text

        if is_over_text:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()

        self._refresh_underline()

    def _refresh_underline(self):
        font = self.font()
        font.setUnderline(self._pointer_over_text or self.hasFocus())
        self.setFont(font)

    def _is_over_rendered_text(self, position):
        text = self.text()

        if not text:
            return False

        content_rect = self.contentsRect()
        metrics = self.fontMetrics()
        text_width = min(metrics.horizontalAdvance(text), content_rect.width())
        text_height = min(metrics.height(), content_rect.height())
        text_top = content_rect.top() + max(
            0,
            (content_rect.height() - text_height) // 2,
        )

        return (
            content_rect.left() <= position.x() < content_rect.left() + text_width
            and text_top <= position.y() < text_top + text_height
        )


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
