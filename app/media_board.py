from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QWidget

from app.media_card import MediaCard, get_media_key


class MediaBoard(QWidget):
    details_requested = Signal(object)

    def __init__(self, rows, columns, parent=None):
        super().__init__(parent)

        self.rows = rows
        self.columns = columns
        self.cards = []
        self.filtered_media = None

        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 12, 0, 0)
        self.layout.setHorizontalSpacing(12)
        self.layout.setVerticalSpacing(12)

        self._build_grid()

    def _build_grid(self):
        for row in range(self.rows):
            for column in range(self.columns):
                card = MediaCard()
                card.set_media_provider_callbacks(
                    self.take_next_media_for_card,
                    self.has_next_media_for_card,
                )
                card.state_changed.connect(self.refresh_card_navigation)
                card.details_requested.connect(self.details_requested.emit)
                self.cards.append(card)
                self.layout.addWidget(card, row, column)

        for column in range(self.columns):
            self.layout.setColumnStretch(column, 1)

        for row in range(self.rows):
            self.layout.setRowStretch(row, 1)

    def load_media(self, filtered_media):
        self.filtered_media = filtered_media
        media_list = filtered_media.media_list if filtered_media else []
        media_by_key = {
            get_media_key(media_draft): media_draft
            for media_draft in media_list
            if get_media_key(media_draft) is not None
        }
        reserved_keys = set()

        for card in self.cards:
            if not card.is_pinned:
                continue

            media_key = card.get_current_media_key()
            refreshed_media = media_by_key.get(media_key)

            if refreshed_media is None or media_key in reserved_keys:
                card.clear_pinned()
                continue

            card.init_card_session(filtered_media, refreshed_media)
            reserved_keys.add(media_key)

        for card in self.cards:
            if card.is_pinned:
                continue

            media_draft = self._take_next_unique_media(filtered_media, reserved_keys)

            if media_draft is None:
                card.clear_card()
                continue

            card.init_card_session(filtered_media, media_draft)

            media_key = get_media_key(media_draft)
            if media_key is not None:
                reserved_keys.add(media_key)

        self.refresh_card_navigation()

    def take_next_media_for_card(self, card):
        filtered_media = card.filtered_media or self.filtered_media
        excluded_keys = self._visible_media_keys()
        self._add_card_current_key(excluded_keys, card)
        return self._take_next_unique_media(filtered_media, excluded_keys)

    def has_next_media_for_card(self, card):
        filtered_media = card.filtered_media or self.filtered_media
        excluded_keys = self._visible_media_keys()
        self._add_card_current_key(excluded_keys, card)
        return self._has_unique_media(filtered_media, excluded_keys)

    def refresh_card_navigation(self):
        for card in self.cards:
            card.refresh_navigation_buttons()

    def _visible_media_keys(self, pinned_only=False):
        keys = set()

        for card in self.cards:
            if pinned_only and not card.is_pinned:
                continue

            if not card.has_visible_media():
                continue

            media_key = card.get_current_media_key()
            if media_key is not None:
                keys.add(media_key)

        return keys

    def _add_card_current_key(self, keys, card):
        media_key = card.get_current_media_key()

        if media_key is not None:
            keys.add(media_key)

    def _take_next_unique_media(self, filtered_media, excluded_keys):
        media_list = filtered_media.media_list if filtered_media else []

        if not media_list:
            return None

        start_index = filtered_media.next_media_index % len(media_list)

        for offset in range(len(media_list)):
            media_index = (start_index + offset) % len(media_list)
            media_draft = media_list[media_index]
            media_key = get_media_key(media_draft)

            if media_key is None or media_key in excluded_keys:
                continue

            filtered_media.next_media_index = (media_index + 1) % len(media_list)
            return media_draft

        return None

    def _has_unique_media(self, filtered_media, excluded_keys):
        media_list = filtered_media.media_list if filtered_media else []

        if not media_list:
            return False

        for media_draft in media_list:
            media_key = get_media_key(media_draft)

            if media_key is not None and media_key not in excluded_keys:
                return True

        return False

    def _clear_grid(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.cards = []

    def set_grid_size(self, rows, columns):
        self._clear_grid()
        self.rows = rows
        self.columns = columns
        self._build_grid()



        #for index, card in enumerate(self.cards):
        #    if index < len(media_list):
        #        card.set_media(media_list[index])
        #    else:
        #        card.clear()
