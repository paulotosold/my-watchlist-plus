from __future__ import annotations

from math import ceil

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from app.media_card import MediaCard, get_media_key


MIN_POSTERS_PER_ROW = 3
DEFAULT_POSTERS_PER_ROW = 5
MAX_POSTERS_PER_ROW = 10

BOARD_TOP_MARGIN = 12
BOARD_SPACING = 12
POSTER_ASPECT_HEIGHT = 3
POSTER_ASPECT_WIDTH = 2


class MediaBoard(QWidget):
    details_requested = Signal(object)

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
        self.card_width = 0
        self.card_height = 0
        self.row_count = 0
        self._content_height = 0
        self._last_reflow_width = None
        self._layout_width = None

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        self.grid_layout = QGridLayout(self)
        self.grid_layout.setContentsMargins(0, BOARD_TOP_MARGIN, 0, 0)
        self.grid_layout.setHorizontalSpacing(BOARD_SPACING)
        self.grid_layout.setVerticalSpacing(BOARD_SPACING)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.timeout.connect(self.reflow_cards)

    def load_media(self, filtered_media):
        self.filtered_media = filtered_media
        media_list = list(
            filtered_media.media_list if filtered_media else []
        )
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
        self.reflow_cards()

    def set_posters_per_row(self, posters_per_row):
        clamped_value = self._clamp_posters_per_row(posters_per_row)

        if clamped_value == self.posters_per_row:
            return False

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

        self.cards.remove(card)
        self._dispose_card(card)
        self.reflow_cards()

    def reflow_cards(self):
        if self._reflow_timer.isActive():
            self._reflow_timer.stop()

        self._last_reflow_width = self.width()

        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        left, top, right, bottom = self.grid_layout.getContentsMargins()
        spacing = self.grid_layout.horizontalSpacing()
        spacing_width = spacing * max(0, self.posters_per_row - 1)
        layout_width = min(
            self.width(),
            self._layout_width
            if self._layout_width is not None
            else self.width(),
        )
        available_width = max(
            1,
            layout_width - left - right - spacing_width,
        )
        self.card_width = max(
            1,
            available_width // self.posters_per_row,
        )
        self.card_height = max(
            1,
            round(
                self.card_width
                * POSTER_ASPECT_HEIGHT
                / POSTER_ASPECT_WIDTH
            ),
        )

        for index, card in enumerate(self.cards):
            row, column = divmod(index, self.posters_per_row)
            card.setFixedSize(self.card_width, self.card_height)
            self.grid_layout.addWidget(card, row, column)
            card.show()

        self.row_count = ceil(
            len(self.cards) / self.posters_per_row
        ) if self.cards else 0
        rows_height = self.row_count * self.card_height
        rows_spacing = (
            max(0, self.row_count - 1)
            * self.grid_layout.verticalSpacing()
        )
        self._content_height = (
            top + bottom + rows_height + rows_spacing
            if self.cards
            else 0
        )

        self.setMinimumHeight(self._content_height)
        self.grid_layout.invalidate()
        self.grid_layout.activate()
        self.updateGeometry()

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
        card.dismiss_requested.connect(
            lambda current_card=card: self.dismiss_card(current_card)
        )
        return card

    def _dispose_card(self, card):
        self.grid_layout.removeWidget(card)
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
