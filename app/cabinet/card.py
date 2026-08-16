"""Poster-only card used by the Cabinet board."""

from app.ui.poster_card import PosterCard


class CabinetCard(PosterCard):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            initial_poster_mode="default_first",
            drag_enabled=True,
        )

    def load_media(self, media_draft):
        self.init_card_session(None, media_draft)
