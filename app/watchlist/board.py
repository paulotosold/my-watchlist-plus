from __future__ import annotations

from collections import defaultdict, deque
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

from .card import MediaCard, get_media_key


MIN_POSTERS_PER_ROW = 2
DEFAULT_POSTERS_PER_ROW = 6
MAX_POSTERS_PER_ROW = 8

BOARD_TOP_MARGIN = 12
BOARD_BOTTOM_MARGIN = 12
BOARD_SPACING = 10
POSTER_ASPECT_HEIGHT = 3
POSTER_ASPECT_WIDTH = 2
WATCHLIST_DRAG_MIME = "application/x-my-watchlist-plus-watchlist-media-id"
REFLOW_ANIMATION_MS = 160
AUTO_SCROLL_MARGIN = 56
AUTO_SCROLL_STEP = 22


class MediaBoard(QWidget):
    details_requested = Signal(object)
    view_state_changed = Signal(int, int, bool)

    def __init__(
        self,
        posters_per_row=DEFAULT_POSTERS_PER_ROW,
        parent=None,
    ):
        super().__init__(parent)

        self.posters_per_row = self._clamp_posters_per_row(
            posters_per_row
        )
        self.cards = []
        self.filtered_media = None
        self._pinned_only = False
        self.card_width = 0
        self.card_height = 0
        self.row_count = 0
        self._content_height = 0
        self._last_reflow_width = None
        self._layout_width = None
        self._animation_group = None
        self._scroll_area = None
        self._last_drag_global_position = None

        self._drag_card = None
        self._drag_original_cards = None
        self._preview_cards = None
        self._preview_index = None
        self._drop_confirmed = False

        self.setAcceptDrops(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

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
        cards = self._preview_cards
        if cards is None:
            cards = self.cards
        return [card.get_current_media_key() for card in cards]

    @property
    def visible_cards(self):
        return self._visible_cards_for(self.cards)

    @property
    def preview_visible_cards(self):
        cards = self._preview_cards
        if cards is None:
            cards = self.cards
        return self._visible_cards_for(cards)

    @property
    def pinned_count(self):
        return sum(card.is_pinned for card in self.cards)

    @property
    def pinned_only(self):
        return self._pinned_only

    def set_scroll_area(self, scroll_area):
        self._scroll_area = scroll_area

    def load_media(self, filtered_media, *, reset_order=False):
        self.cancel_drag()
        self.filtered_media = filtered_media
        media_list = list(
            filtered_media.media_list if filtered_media else []
        )

        if reset_order:
            self._load_media_for_explicit_reset(filtered_media, media_list)
        else:
            self._load_media_preserving_pinned_slots(filtered_media, media_list)

        self._leave_pinned_only_if_empty()
        self.reflow_cards()
        self._emit_view_state_changed()

    def _load_media_preserving_pinned_slots(
        self,
        filtered_media,
        media_list,
    ):
        media_by_key = {}

        for media_draft in media_list:
            media_key = get_media_key(media_draft)

            if media_key is not None and media_key not in media_by_key:
                media_by_key[media_key] = media_draft

        old_cards = list(self.cards)
        target_cards = [None] * len(media_list)
        used_cards = set()
        reserved_keys = set()

        for old_index, card in enumerate(old_cards):
            if not card.is_pinned:
                continue

            media_key = card.get_current_media_key()
            refreshed_media = media_by_key.get(media_key)

            if refreshed_media is None or media_key in reserved_keys:
                card.clear_pinned()
                continue

            target_index = self._nearest_free_index(
                target_cards,
                old_index,
            )

            if target_index is None:
                card.clear_pinned()
                continue

            card.init_card_session(filtered_media, refreshed_media)
            target_cards[target_index] = card
            used_cards.add(card)
            reserved_keys.add(media_key)

        reusable_cards = [
            card for card in old_cards if card not in used_cards
        ]
        unmatched_reserved_keys = set(reserved_keys)
        remaining_media = []

        for media_draft in media_list:
            media_key = get_media_key(media_draft)

            if media_key in unmatched_reserved_keys:
                unmatched_reserved_keys.remove(media_key)
                continue

            remaining_media.append(media_draft)

        media_iterator = iter(remaining_media)

        for index, card in enumerate(target_cards):
            if card is not None:
                continue

            try:
                media_draft = next(media_iterator)
            except StopIteration:
                break

            if reusable_cards:
                card = reusable_cards.pop(0)
                card.clear_pinned()
            else:
                card = self._create_card()

            card.init_card_session(filtered_media, media_draft)
            target_cards[index] = card
            used_cards.add(card)

        for card in reusable_cards:
            self._dispose_card(card)

        self.cards = [card for card in target_cards if card is not None]

    def _load_media_for_explicit_reset(self, filtered_media, media_list):
        old_cards = list(self.cards)
        media_indexes_by_key = defaultdict(deque)

        for index, media_draft in enumerate(media_list):
            media_indexes_by_key[get_media_key(media_draft)].append(index)

        pinned_entries = []
        reserved_media_indexes = set()
        reserved_cards = set()

        for card in old_cards:
            if not card.is_pinned:
                continue

            matching_indexes = media_indexes_by_key.get(
                card.get_current_media_key()
            )
            if not matching_indexes:
                card.clear_pinned()
                continue

            media_index = matching_indexes.popleft()
            pinned_entries.append([card, media_list[media_index]])
            reserved_media_indexes.add(media_index)
            reserved_cards.add(card)

        target_entries = pinned_entries + [
            [None, media_draft]
            for index, media_draft in enumerate(media_list)
            if index not in reserved_media_indexes
        ]
        cards_by_key = defaultdict(deque)

        for card in old_cards:
            if card in reserved_cards:
                continue
            cards_by_key[card.get_current_media_key()].append(card)

        used_cards = set(reserved_cards)
        for target_entry in target_entries[len(pinned_entries):]:
            _card, media_draft = target_entry
            media_key = get_media_key(media_draft)
            matching_cards = cards_by_key.get(media_key)
            card = matching_cards.popleft() if matching_cards else None
            if card is not None:
                used_cards.add(card)
                target_entry[0] = card

        reusable_cards = deque(
            card for card in old_cards if card not in used_cards
        )

        for target_entry in target_entries:
            card, media_draft = target_entry

            if card is None:
                if reusable_cards:
                    card = reusable_cards.popleft()
                    card.clear_pinned()
                else:
                    card = self._create_card()
                target_entry[0] = card

            card.init_card_session(filtered_media, media_draft)

        for card in reusable_cards:
            self._dispose_card(card)

        self.cards = [card for card, _media_draft in target_entries]

    def reconcile_media(self, filtered_media, previously_filtered_media):
        """Refresh visible cards without rebuilding the current grid order."""
        self.cancel_drag()
        self.filtered_media = filtered_media
        media_list = list(
            filtered_media.media_list if filtered_media else []
        )
        previous_media_keys = {
            get_media_key(media_draft)
            for media_draft in previously_filtered_media
            if get_media_key(media_draft) is not None
        }
        refreshed_media_by_key = {}

        for media_draft in media_list:
            media_key = get_media_key(media_draft)

            if media_key is not None and media_key not in refreshed_media_by_key:
                refreshed_media_by_key[media_key] = media_draft

        reconciled_cards = []
        reused_media_keys = set()

        for card in list(self.cards):
            media_key = card.get_current_media_key()
            refreshed_media = refreshed_media_by_key.get(media_key)

            if refreshed_media is None or media_key in reused_media_keys:
                self._dispose_card(card)
                continue

            card.init_card_session(filtered_media, refreshed_media)
            reconciled_cards.append(card)
            reused_media_keys.add(media_key)

        for media_draft in media_list:
            media_key = get_media_key(media_draft)

            if (
                media_key is None
                or media_key in previous_media_keys
                or media_key in reused_media_keys
            ):
                continue

            card = self._create_card()
            card.init_card_session(filtered_media, media_draft)
            reconciled_cards.append(card)
            reused_media_keys.add(media_key)

        self.cards = reconciled_cards
        self._leave_pinned_only_if_empty()
        self.reflow_cards()
        self._emit_view_state_changed()

    def set_pinned_only(self, pinned_only):
        pinned_only = bool(pinned_only)

        if pinned_only and self.pinned_count == 0:
            pinned_only = False

        if pinned_only == self._pinned_only:
            return False

        self.cancel_drag()
        self._pinned_only = pinned_only
        self.reflow_cards()
        self._emit_view_state_changed()
        return True

    def clear_all_pins(self):
        pinned_cards = [card for card in self.cards if card.is_pinned]

        if not pinned_cards:
            return False

        self.cancel_drag()
        for card in pinned_cards:
            card.clear_pinned()

        self._pinned_only = False
        self.reflow_cards()
        self._emit_view_state_changed()
        return True

    def set_posters_per_row(self, posters_per_row):
        clamped_value = self._clamp_posters_per_row(posters_per_row)

        if clamped_value == self.posters_per_row:
            return False

        self.cancel_drag()
        self.posters_per_row = clamped_value
        self.reflow_cards()
        return True

    def set_layout_width(self, layout_width):
        layout_width = max(1, int(layout_width))

        if layout_width == self._layout_width:
            return False

        self._layout_width = layout_width
        return True

    def dismiss_card(self, card):
        if card not in self.cards:
            return

        self.cancel_drag()
        self.cards.remove(card)
        self._dispose_card(card)
        self._leave_pinned_only_if_empty()
        self.reflow_cards()
        self._emit_view_state_changed()

    def slot_rects(self, count=None):
        if count is None:
            count = len(self.visible_cards)
        count = max(0, int(count))
        layout_width = min(
            max(1, self.width()),
            self._layout_width
            if self._layout_width is not None
            else max(1, self.width()),
        )
        spacing_width = BOARD_SPACING * max(0, self.posters_per_row - 1)
        available_width = max(1, layout_width - spacing_width)
        card_width = max(1, available_width // self.posters_per_row)
        cards_width = card_width * self.posters_per_row
        unused_width = max(
            0,
            layout_width - cards_width - spacing_width,
        )
        left_margin = unused_width // 2
        card_height = max(
            1,
            round(
                card_width
                * POSTER_ASPECT_HEIGHT
                / POSTER_ASPECT_WIDTH
            ),
        )
        return [
            QRect(
                left_margin + column * (card_width + BOARD_SPACING),
                BOARD_TOP_MARGIN + row * (card_height + BOARD_SPACING),
                card_width,
                card_height,
            )
            for row, column in (
                divmod(index, self.posters_per_row)
                for index in range(count)
            )
        ]

    def target_index_at(self, position):
        visible_count = len(self.preview_visible_cards)
        if visible_count == 0:
            return 0
        rects = self.slot_rects(visible_count)
        first = rects[0]
        horizontal_step = first.width() + BOARD_SPACING
        vertical_step = first.height() + BOARD_SPACING
        column = round((position.x() - first.center().x()) / horizontal_step)
        row = round((position.y() - first.center().y()) / vertical_step)
        column = max(0, min(self.posters_per_row - 1, column))
        row = max(0, row)
        return max(
            0,
            min(visible_count - 1, row * self.posters_per_row + column),
        )

    def reflow_cards(self):
        if self._reflow_timer.isActive():
            self._reflow_timer.stop()

        self._stop_animation()
        self._last_reflow_width = self.width()
        ordered_cards = self.preview_visible_cards
        rects = self.slot_rects(len(ordered_cards))
        self.card_width = rects[0].width() if rects else 0
        self.card_height = rects[0].height() if rects else 0
        visible_card_set = set(ordered_cards)

        for card in self.cards:
            if card not in visible_card_set:
                card.hide()

        for index, card in enumerate(ordered_cards):
            card.setGeometry(rects[index])
            if card is not self._drag_card:
                card.show()

        self.row_count = (
            ceil(len(ordered_cards) / self.posters_per_row)
            if ordered_cards
            else 0
        )
        self._content_height = (
            rects[-1].bottom() + 1 + BOARD_BOTTOM_MARGIN
            if rects
            else 0
        )

        self.setMinimumHeight(self._content_height)
        self.updateGeometry()

    def preview_reorder(self, card, target_index):
        base_cards = list(self._drag_original_cards or self.cards)
        base_visible_cards = self._visible_cards_for(base_cards)

        if card not in base_visible_cards or len(base_visible_cards) < 2:
            return False

        target_index = max(
            0,
            min(len(base_visible_cards) - 1, int(target_index)),
        )
        if self._preview_index == target_index:
            return False

        desired_visible_cards = list(base_visible_cards)
        desired_visible_cards.remove(card)
        desired_visible_cards.insert(target_index, card)

        if self._pinned_only:
            preview_cards = self._canonical_order_for_pinned_move(
                base_cards,
                card,
                desired_visible_cards,
            )
        else:
            preview_cards = desired_visible_cards

        self._preview_cards = preview_cards
        self._preview_index = target_index
        self._animate_preview()
        return True

    def commit_preview(self):
        if self._drag_original_cards is None or self._preview_cards is None:
            return False

        self.cards = list(self._preview_cards)
        self._drop_confirmed = True
        self._finish_drag_layout()
        return True

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
        if self._is_current_watchlist_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self._is_current_watchlist_drag(event):
            event.ignore()
            return

        self._last_drag_global_position = self.mapToGlobal(
            event.position().toPoint()
        )
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
            original_visible_cards = self._visible_cards_for(
                self._drag_original_cards
            )
            original_index = original_visible_cards.index(self._drag_card)
            self._preview_index = None
            self.preview_reorder(self._drag_card, original_index)
        event.accept()

    def dropEvent(self, event):
        self._auto_scroll_timer.stop()
        if (
            not self._is_current_watchlist_drag(event)
            or self._preview_cards is None
        ):
            event.ignore()
            self.reject_reorder()
            return

        if self.commit_preview():
            event.acceptProposedAction()
        else:
            event.ignore()

    def schedule_reflow(self):
        self._reflow_timer.start(0)

    def minimumSizeHint(self):
        return QSize(0, self._content_height)

    def sizeHint(self):
        return QSize(max(0, self.width()), self._content_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if event.size().width() != self._last_reflow_width:
            self.schedule_reflow()

    def _create_card(self):
        card = MediaCard(self)
        card.details_requested.connect(self.details_requested.emit)
        card.drag_requested.connect(self._start_card_drag)
        card.state_changed.connect(
            lambda current_card=card: self._on_card_state_changed(
                current_card
            )
        )
        card.dismiss_requested.connect(
            lambda current_card=card: self.dismiss_card(current_card)
        )
        return card

    def _on_card_state_changed(self, card):
        if card not in self.cards:
            return

        self.cancel_drag()
        self._leave_pinned_only_if_empty()
        self.reflow_cards()
        self._emit_view_state_changed()

    def _start_card_drag(self, card, hotspot):
        visible_cards = self.visible_cards
        if card not in visible_cards or len(visible_cards) < 2:
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
        self._preview_index = visible_cards.index(card)
        self._drop_confirmed = False
        card.hide()

        mime_data = QMimeData()
        mime_data.setData(
            WATCHLIST_DRAG_MIME,
            str(card.get_current_media_key()).encode(),
        )
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
        preview_cards = self.preview_visible_cards
        rects = self.slot_rects(len(preview_cards))
        group = QParallelAnimationGroup(self)

        for index, card in enumerate(preview_cards):
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
        viewport_position = viewport.mapFromGlobal(
            self._last_drag_global_position
        )
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
                board_position = self.mapFromGlobal(
                    self._last_drag_global_position
                )
                self.preview_reorder(
                    self._drag_card,
                    self.target_index_at(board_position),
                )

    def _is_current_watchlist_drag(self, event):
        return (
            self._drag_card is not None
            and event.source() is self._drag_card
            and event.mimeData().hasFormat(WATCHLIST_DRAG_MIME)
        )

    def _canonical_order_for_pinned_move(
        self,
        base_cards,
        moved_card,
        desired_visible_cards,
    ):
        canonical_cards = list(base_cards)
        canonical_cards.remove(moved_card)
        moved_index = desired_visible_cards.index(moved_card)

        if moved_index + 1 < len(desired_visible_cards):
            next_pinned_card = desired_visible_cards[moved_index + 1]
            target_index = canonical_cards.index(next_pinned_card)
        else:
            previous_pinned_card = desired_visible_cards[moved_index - 1]
            target_index = canonical_cards.index(previous_pinned_card) + 1

        canonical_cards.insert(target_index, moved_card)
        return canonical_cards

    def _visible_cards_for(self, cards):
        if not self._pinned_only:
            return list(cards)
        return [card for card in cards if card.is_pinned]

    def _leave_pinned_only_if_empty(self):
        if self._pinned_only and self.pinned_count == 0:
            self._pinned_only = False

    def _emit_view_state_changed(self):
        self.view_state_changed.emit(
            len(self.cards),
            self.pinned_count,
            self._pinned_only,
        )

    def _dispose_card(self, card):
        card.hide()
        card.setParent(None)
        card.deleteLater()

    @staticmethod
    def _nearest_free_index(slots, preferred_index):
        if not slots:
            return None

        preferred_index = max(0, min(preferred_index, len(slots) - 1))

        for distance in range(len(slots)):
            right_index = preferred_index + distance

            if right_index < len(slots) and slots[right_index] is None:
                return right_index

            left_index = preferred_index - distance

            if left_index >= 0 and slots[left_index] is None:
                return left_index

        return None

    @staticmethod
    def _clamp_posters_per_row(posters_per_row):
        return max(
            MIN_POSTERS_PER_ROW,
            min(MAX_POSTERS_PER_ROW, int(posters_per_row)),
        )
