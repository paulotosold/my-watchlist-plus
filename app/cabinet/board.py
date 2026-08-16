"""Animated, persistable drag-reorder board for Cabinet media."""

from math import ceil

from PySide6.QtCore import (
    QEasingCurve,
    QMimeData,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QDrag, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from .card import CabinetCard


MIN_POSTERS_PER_ROW = 4
DEFAULT_POSTERS_PER_ROW = 10
MAX_POSTERS_PER_ROW = 20
BOARD_TOP_MARGIN = 12
BOARD_BOTTOM_MARGIN = 12
BOARD_HORIZONTAL_SPACING = 25
BOARD_VERTICAL_SPACING = 25
POSTER_ASPECT_HEIGHT = 3
POSTER_ASPECT_WIDTH = 2
CABINET_DRAG_MIME = "application/x-my-watchlist-plus-cabinet-media-id"
REFLOW_ANIMATION_MS = 160
AUTO_SCROLL_MARGIN = 56
AUTO_SCROLL_STEP = 22


class CabinetBoard(QWidget):
    details_requested = Signal(object)
    view_state_changed = Signal(int, int)
    reorder_requested = Signal(object, object)

    def __init__(self, posters_per_row=DEFAULT_POSTERS_PER_ROW, parent=None):
        super().__init__(parent)
        self.posters_per_row = self._clamp_posters_per_row(posters_per_row)
        self.cards = []
        self.card_width = 0
        self.card_height = 0
        self.row_count = 0
        self._content_height = 0
        self._layout_width = None
        self._last_reflow_width = None
        self._animation_group = None
        self._scroll_area = None
        self._last_drag_global_position = None

        self._drag_card = None
        self._drag_original_cards = None
        self._preview_cards = None
        self._preview_index = None
        self._drop_confirmed = False

        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.timeout.connect(self.reflow_cards)
        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(16)
        self._auto_scroll_timer.timeout.connect(self._auto_scroll)

    @property
    def media_ids(self):
        return [card.get_current_media_key() for card in self.cards]

    @property
    def preview_media_ids(self):
        cards = self._preview_cards or self.cards
        return [card.get_current_media_key() for card in cards]

    def set_scroll_area(self, scroll_area):
        self._scroll_area = scroll_area

    def load_media(self, media_drafts):
        self.cancel_drag()
        for card in self.cards:
            self._dispose_card(card)
        self.cards = []
        for media_draft in media_drafts:
            card = CabinetCard(self)
            card.load_media(media_draft)
            card.details_requested.connect(self.details_requested.emit)
            card.drag_requested.connect(self._start_card_drag)
            self.cards.append(card)
        self.reflow_cards()
        self.view_state_changed.emit(len(self.cards), self.posters_per_row)

    def set_posters_per_row(self, posters_per_row):
        clamped = self._clamp_posters_per_row(posters_per_row)
        if clamped == self.posters_per_row:
            return False
        self.posters_per_row = clamped
        self.reflow_cards()
        self.view_state_changed.emit(len(self.cards), self.posters_per_row)
        return True

    def set_layout_width(self, layout_width):
        layout_width = max(1, int(layout_width))
        if layout_width == self._layout_width:
            return False
        self._layout_width = layout_width
        return True

    def slot_rects(self, count=None):
        count = len(self.cards) if count is None else max(0, int(count))
        layout_width = min(
            max(1, self.width()),
            self._layout_width if self._layout_width is not None else max(1, self.width()),
        )
        spacing_width = BOARD_HORIZONTAL_SPACING * max(0, self.posters_per_row - 1)
        available_width = max(1, layout_width - spacing_width)
        card_width = max(1, available_width // self.posters_per_row)
        cards_width = card_width * self.posters_per_row
        unused_width = max(0, layout_width - cards_width - spacing_width)
        left_margin = unused_width // 2
        card_height = max(
            1,
            round(card_width * POSTER_ASPECT_HEIGHT / POSTER_ASPECT_WIDTH),
        )
        return [
            QRect(
                left_margin + column * (card_width + BOARD_HORIZONTAL_SPACING),
                BOARD_TOP_MARGIN + row * (card_height + BOARD_VERTICAL_SPACING),
                card_width,
                card_height,
            )
            for row, column in (
                divmod(index, self.posters_per_row) for index in range(count)
            )
        ]

    def target_index_at(self, position):
        if not self.cards:
            return 0
        rects = self.slot_rects()
        first = rects[0]
        horizontal_step = first.width() + BOARD_HORIZONTAL_SPACING
        vertical_step = first.height() + BOARD_VERTICAL_SPACING
        column = round((position.x() - first.center().x()) / horizontal_step)
        row = round((position.y() - first.center().y()) / vertical_step)
        column = max(0, min(self.posters_per_row - 1, column))
        row = max(0, row)
        return max(0, min(len(self.cards) - 1, row * self.posters_per_row + column))

    def reflow_cards(self):
        if self._reflow_timer.isActive():
            self._reflow_timer.stop()
        self._stop_animation()
        self._last_reflow_width = self.width()
        rects = self.slot_rects()
        self.card_width = rects[0].width() if rects else 0
        self.card_height = rects[0].height() if rects else 0
        ordered_cards = self._preview_cards or self.cards
        for index, card in enumerate(ordered_cards):
            card.setGeometry(rects[index])
            if card is not self._drag_card:
                card.show()
        self.row_count = ceil(len(self.cards) / self.posters_per_row) if self.cards else 0
        self._content_height = (
            rects[-1].bottom() + 1 + BOARD_BOTTOM_MARGIN if rects else 0
        )
        self.setMinimumHeight(self._content_height)
        self.updateGeometry()

    def preview_reorder(self, card, target_index):
        if card not in self.cards:
            return False
        target_index = max(0, min(len(self.cards) - 1, int(target_index)))
        if self._preview_index == target_index:
            return False
        base_cards = list(self._drag_original_cards or self.cards)
        base_cards.remove(card)
        base_cards.insert(target_index, card)
        self._preview_cards = base_cards
        self._preview_index = target_index
        self._animate_preview()
        return True

    def confirm_reorder(self, result):
        if self._drag_original_cards is None or self._preview_cards is None:
            return False
        orders = (result or {}).get("orders") or {}
        self.cards = list(self._preview_cards)
        for card in self.cards:
            media_id = card.get_current_media_key()
            card.current_media.setdefault("user_data", {})["cabinet_order"] = orders.get(media_id)
        self._drop_confirmed = True
        self._finish_drag_layout()
        return True

    def commit_preview(self):
        if self._drag_original_cards is None or self._preview_cards is None:
            return False
        expected = [card.get_current_media_key() for card in self._drag_original_cards]
        desired = [card.get_current_media_key() for card in self._preview_cards]
        self._drop_confirmed = False
        self.reorder_requested.emit(expected, desired)
        if self._drop_confirmed:
            return True
        self.reject_reorder()
        return False

    def reject_reorder(self):
        if self._drag_original_cards is not None:
            self.cards = list(self._drag_original_cards)
        self._drop_confirmed = False
        self._finish_drag_layout()
        self._reset_drag_state()

    def cancel_drag(self):
        if self._drag_original_cards is not None:
            self.cards = list(self._drag_original_cards)
        self._drop_confirmed = False
        self._finish_drag_layout()
        self._reset_drag_state()

    def dragEnterEvent(self, event):
        if self._is_current_cabinet_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self._is_current_cabinet_drag(event):
            event.ignore()
            return
        self._last_drag_global_position = self.mapToGlobal(event.position().toPoint())
        self.preview_reorder(
            self._drag_card,
            self.target_index_at(event.position().toPoint()),
        )
        if not self._auto_scroll_timer.isActive():
            self._auto_scroll_timer.start()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._auto_scroll_timer.stop()
        if self._drag_original_cards is not None and self._drag_card is not None:
            original_index = self._drag_original_cards.index(self._drag_card)
            self._preview_index = None
            self.preview_reorder(self._drag_card, original_index)
        event.accept()

    def dropEvent(self, event):
        self._auto_scroll_timer.stop()
        if not self._is_current_cabinet_drag(event) or self._preview_cards is None:
            event.ignore()
            self.reject_reorder()
            return
        if self.commit_preview():
            event.acceptProposedAction()
        else:
            event.ignore()

    def minimumSizeHint(self):
        return QSize(0, self._content_height)

    def sizeHint(self):
        return QSize(max(0, self.width()), self._content_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != self._last_reflow_width:
            self._reflow_timer.start(0)

    def _start_card_drag(self, card, hotspot):
        if card not in self.cards or len(self.cards) < 2:
            return
        ghost_source = card.grab()
        ghost = QPixmap(ghost_source.size())
        ghost.fill(Qt.GlobalColor.transparent)
        painter = QPainter(ghost)
        painter.setOpacity(0.58)
        painter.drawPixmap(0, 0, ghost_source)
        painter.end()

        self._drag_card = card
        self._drag_original_cards = list(self.cards)
        self._preview_cards = list(self.cards)
        self._preview_index = self.cards.index(card)
        self._drop_confirmed = False
        card.hide()

        mime_data = QMimeData()
        mime_data.setData(CABINET_DRAG_MIME, str(card.get_current_media_key()).encode())
        drag = QDrag(card)
        drag.setMimeData(mime_data)
        drag.setPixmap(ghost)
        drag.setHotSpot(hotspot)
        result = drag.exec(Qt.DropAction.MoveAction)
        if result != Qt.DropAction.MoveAction or not self._drop_confirmed:
            self.cancel_drag()
        else:
            self._reset_drag_state()

    def _animate_preview(self):
        self._stop_animation()
        rects = self.slot_rects()
        group = QParallelAnimationGroup(self)
        for index, card in enumerate(self._preview_cards):
            if card is self._drag_card:
                continue
            animation = QPropertyAnimation(card, b"geometry", group)
            animation.setDuration(REFLOW_ANIMATION_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.setStartValue(card.geometry())
            animation.setEndValue(rects[index])
            group.addAnimation(animation)
        self._animation_group = group
        group.start()

    def _finish_drag_layout(self):
        dragged_card = self._drag_card
        self._auto_scroll_timer.stop()
        self._stop_animation()
        self._preview_cards = list(self.cards)
        self.reflow_cards()
        if dragged_card is not None:
            dragged_card.show()
        self._preview_cards = None

    def _reset_drag_state(self):
        self._drag_card = None
        self._drag_original_cards = None
        self._preview_cards = None
        self._preview_index = None
        self._last_drag_global_position = None
        self._auto_scroll_timer.stop()

    def _stop_animation(self):
        if self._animation_group is not None:
            self._animation_group.stop()
            self._animation_group = None

    def _auto_scroll(self):
        if self._scroll_area is None or self._last_drag_global_position is None:
            return
        viewport = self._scroll_area.viewport()
        viewport_position = viewport.mapFromGlobal(self._last_drag_global_position)
        delta = 0
        if viewport_position.y() < AUTO_SCROLL_MARGIN:
            delta = -AUTO_SCROLL_STEP
        elif viewport_position.y() > viewport.height() - AUTO_SCROLL_MARGIN:
            delta = AUTO_SCROLL_STEP
        if delta:
            scroll_bar = self._scroll_area.verticalScrollBar()
            previous_value = scroll_bar.value()
            scroll_bar.setValue(previous_value + delta)
            if scroll_bar.value() != previous_value and self._drag_card is not None:
                board_position = self.mapFromGlobal(self._last_drag_global_position)
                self.preview_reorder(
                    self._drag_card,
                    self.target_index_at(board_position),
                )

    def _is_current_cabinet_drag(self, event):
        return (
            self._drag_card is not None
            and event.source() is self._drag_card
            and event.mimeData().hasFormat(CABINET_DRAG_MIME)
        )

    def _dispose_card(self, card):
        card.hide()
        card.setParent(None)
        card.deleteLater()

    @staticmethod
    def _clamp_posters_per_row(posters_per_row):
        return max(
            MIN_POSTERS_PER_ROW,
            min(MAX_POSTERS_PER_ROW, int(posters_per_row)),
        )
