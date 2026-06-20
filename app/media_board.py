from PySide6.QtWidgets import QGridLayout, QWidget

from app.media_card import MediaCard

class MediaBoard(QWidget):
    def __init__(self, rows, columns, parent=None):
        super().__init__(parent)

        self.rows = rows
        self.columns = columns
        self.cards = []

        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 12, 0, 0)
        self.layout.setHorizontalSpacing(12)
        self.layout.setVerticalSpacing(12)

        self._build_grid()

    def _build_grid(self):
        for row in range(self.rows):
            for column in range(self.columns):
                card = MediaCard()
                self.cards.append(card)
                self.layout.addWidget(card, row, column)

        for column in range(self.columns):
            self.layout.setColumnStretch(column, 1)

        for row in range(self.rows):
            self.layout.setRowStretch(row, 1)

    def load_media(self, filtered_media):
        media_count = len(filtered_media.media_list)
        loaded_cards = 0

        for card in self.cards:
            if card.is_pinned:
                continue

            if media_count == 0 or loaded_cards >= media_count:
                card.clear_card()
                continue

            card.init_card_session(filtered_media)
            loaded_cards += 1

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
