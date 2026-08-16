"""Watchlist-specific controls layered on the shared poster card."""

import random

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QLabel

from app.paths import ASSETS_DIR
from app.ui.poster_card import (
    MEDIA_CARD_BUTTON_MARGIN,
    MEDIA_CARD_ICON_DIR,
    MEDIA_CARD_ICON_HEIGHT,
    PosterCard,
    PosterCardOverlay,
    get_media_key,
    icon_dimensions_for_height,
)


_icon_dimensions_for_height = icon_dimensions_for_height
MediaCardOverlay = PosterCardOverlay


class MediaCard(PosterCard):
    state_changed = Signal()
    dismiss_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, initial_poster_mode="random")
        self.is_pinned = False
        self.pin_pixmap = QPixmap(str(ASSETS_DIR / "pinned_overlay.png"))
        self.pin_layer = QLabel(self)
        self.pin_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_layer.setScaledContents(False)
        self.btn_close = self.make_button(
            MEDIA_CARD_ICON_DIR / "close.png", self.overlay_layer
        )
        self.btn_pin = self.make_button(
            MEDIA_CARD_ICON_DIR / "pin.png", self.overlay_layer
        )
        self.btn_close.clicked.connect(self.on_close_clicked)
        self.btn_pin.clicked.connect(self.on_pin_clicked)
        self.poster_layer.lower()
        self.pin_layer.raise_()
        self.overlay_layer.raise_()

    def on_close_clicked(self):
        self.clear_pinned()
        self.dismiss_requested.emit()

    def _get_initial_poster_index(self):
        if not self.poster_filenames:
            return 0
        saved_index = self.poster_index_by_media_key.get(self._get_media_key())
        if saved_index is not None:
            return min(saved_index, len(self.poster_filenames) - 1)
        return random.randrange(len(self.poster_filenames))

    def clear_pinned(self):
        self.is_pinned = False
        self.update_pin_status()

    def on_pin_clicked(self):
        self.is_pinned = not self.is_pinned
        self.update_pin_status()
        self.state_changed.emit()

    def update_pin_status(self):
        icon_name = "unpin.png" if self.is_pinned else "pin.png"
        self.btn_pin.setIcon(QIcon(str(MEDIA_CARD_ICON_DIR / icon_name)))
        if self.is_pinned and not self.pin_pixmap.isNull():
            self._render_pin_overlay()
        else:
            self.pin_layer.clear()

    def clear_card(self):
        self.is_pinned = False
        self.pin_layer.clear()
        self.update_pin_status()
        super().clear_card()

    def hide_card_elements(self):
        self.btn_close.hide()
        self.btn_pin.hide()
        super().hide_card_elements()

    def show_card_elements(self):
        super().show_card_elements()
        self.btn_close.show()
        self.btn_pin.show()

    def _render_pin_overlay(self):
        if (
            not self.is_pinned
            or self.pin_pixmap.isNull()
            or self.pin_layer.size().isEmpty()
        ):
            self.pin_layer.clear()
            return
        self.pin_layer.setPixmap(
            self.pin_pixmap.scaled(
                self.pin_layer.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _layout_buttons(self):
        super()._layout_buttons()
        self.btn_close.move(
            self.width() - self.btn_close.width() - MEDIA_CARD_BUTTON_MARGIN,
            MEDIA_CARD_BUTTON_MARGIN,
        )
        self.btn_pin.move(
            (self.width() - self.btn_pin.width()) // 2,
            self.height() - self.btn_pin.height() - MEDIA_CARD_BUTTON_MARGIN,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.pin_layer.setGeometry(self.rect())
        self._render_pin_overlay()
        self._layout_buttons()
