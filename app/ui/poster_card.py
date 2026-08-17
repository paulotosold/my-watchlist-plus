"""Shared poster-card behavior used by Watchlist and Cabinet."""

from copy import deepcopy
from functools import lru_cache
import random

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QToolButton,
    QWidget,
)

from app.paths import ICONS_DIR, MEDIA_POSTERS_DIR


MEDIA_CARD_ICON_HEIGHT = 32
MEDIA_CARD_BUTTON_MARGIN = 6
MEDIA_CARD_ICON_DIR = ICONS_DIR / "poster_card"
POSTER_DIR = MEDIA_POSTERS_DIR


@lru_cache(maxsize=None)
def icon_dimensions_for_height(icon_img_path, icon_height):
    source_size = QImageReader(str(icon_img_path)).size()
    if (
        not source_size.isValid()
        or source_size.width() <= 0
        or source_size.height() <= 0
    ):
        return icon_height, icon_height
    return (
        max(1, round(icon_height * source_size.width() / source_size.height())),
        icon_height,
    )


def get_media_key(media_draft):
    if not media_draft:
        return None
    return media_draft.get("media_id")


class PosterCardOverlay(QWidget):
    background_clicked = Signal()
    drag_requested = Signal(object)

    def __init__(self, parent=None, *, drag_enabled=False):
        super().__init__(parent)
        self.drag_enabled = bool(drag_enabled)
        self._press_position = None
        self._drag_started = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.childAt(event.position().toPoint()) is None
        ):
            if self.drag_enabled:
                self._press_position = event.position().toPoint()
                self._drag_started = False
            else:
                self.background_clicked.emit()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self.drag_enabled
            and self._press_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self._drag_started
        ):
            distance = (
                event.position().toPoint() - self._press_position
            ).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._drag_started = True
                self.drag_requested.emit(QPoint(self._press_position))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            self.drag_enabled
            and event.button() == Qt.MouseButton.LeftButton
            and self._press_position is not None
            and not self._drag_started
        ):
            self.background_clicked.emit()
        self._press_position = None
        self._drag_started = False
        super().mouseReleaseEvent(event)


class PosterCard(QFrame):
    details_requested = Signal(object)
    drag_requested = Signal(object, object)

    def __init__(
        self,
        parent=None,
        *,
        initial_poster_mode="random",
        drag_enabled=False,
    ):
        super().__init__(parent)
        self.initial_poster_mode = initial_poster_mode
        self.drag_enabled = bool(drag_enabled)
        self.is_disabled = True
        self.filtered_media = None
        self.current_media = None
        self.poster_index = 0
        self.poster_filenames = []
        self.poster_index_by_media_key = {}
        self.poster_pixmap = QPixmap()

        self.poster_layer = QLabel(self)
        self.poster_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_layer.setStyleSheet("background-color: white;")
        self.overlay_layer = PosterCardOverlay(
            self,
            drag_enabled=self.drag_enabled,
        )
        self.overlay_layer.hide()
        self.btn_info = self.make_button(
            MEDIA_CARD_ICON_DIR / "info.png",
            self.overlay_layer,
        )
        self.overlay_layer.background_clicked.connect(self.on_overlay_clicked)
        self.overlay_layer.drag_requested.connect(self._request_drag)
        self.btn_info.clicked.connect(self.request_details)
        self.poster_layer.lower()
        self.overlay_layer.raise_()

    def make_button(self, icon_img_path, parent):
        button = QToolButton(parent)
        icon_size = QSize(
            *icon_dimensions_for_height(icon_img_path, MEDIA_CARD_ICON_HEIGHT)
        )
        button.setFixedSize(icon_size)
        button.setIcon(QIcon(str(icon_img_path)))
        button.setIconSize(icon_size)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
        )
        opacity = QGraphicsOpacityEffect(button)
        opacity.setOpacity(0.9)
        button.setGraphicsEffect(opacity)
        return button

    def set_filtered_media(self, filtered_media):
        self.filtered_media = filtered_media

    def init_card_session(self, filtered_media, media_draft=None):
        self.filtered_media = filtered_media
        self.poster_index = 0
        self.poster_filenames = []
        if media_draft is None:
            self.clear_card()
            self.filtered_media = filtered_media
            return
        self.is_disabled = False
        self.show_card_elements()
        self.load_card_media(media_draft)

    def load_card_media(self, media_draft):
        self.current_media = deepcopy(media_draft)
        posters = self._get_eligible_posters()
        if self.initial_poster_mode == "default_first":
            posters.sort(key=lambda poster: not bool(poster.get("is_default")))
        self.poster_filenames = [poster["filename"] for poster in posters]
        self.poster_index = self._get_initial_poster_index()
        self._save_current_poster_index()
        self.show_card_elements()
        self.update_poster_image()

    def _get_eligible_posters(self):
        posters = self.current_media.get("posters", []) if self.current_media else []
        eligible = []
        seen = set()
        for poster in posters:
            if poster.get("curation_status") not in {"selected", "pending"}:
                continue
            filename = poster.get("filename")
            if (
                not filename
                or filename in seen
                or not self._poster_path(filename).exists()
            ):
                continue
            eligible.append(poster)
            seen.add(filename)
        return eligible

    def _get_poster_filenames(self):
        return [poster["filename"] for poster in self._get_eligible_posters()]

    def _get_initial_poster_index(self):
        if not self.poster_filenames:
            return 0
        saved_index = self.poster_index_by_media_key.get(self._get_media_key())
        if saved_index is not None:
            return min(saved_index, len(self.poster_filenames) - 1)
        if self.initial_poster_mode == "default_first":
            return 0
        return random.randrange(len(self.poster_filenames))

    def update_poster_image(self):
        if not self.poster_filenames:
            self.poster_layer.clear()
            self.poster_pixmap = QPixmap()
            return
        poster_path = self._poster_path(self.poster_filenames[self.poster_index])
        self.poster_pixmap = QPixmap(str(poster_path))
        if self.poster_pixmap.isNull():
            self.poster_layer.clear()
            self.poster_pixmap = QPixmap()
            return
        self._render_poster()

    def on_overlay_clicked(self):
        if self.poster_pixmap.isNull() or not self.poster_filenames:
            return
        self.poster_index = (self.poster_index + 1) % len(self.poster_filenames)
        self._save_current_poster_index()
        self.update_poster_image()

    def request_details(self):
        if self.current_media is not None:
            self.details_requested.emit(deepcopy(self.current_media))

    def show_details_window(self):
        self.request_details()

    def clear_card(self):
        self.is_disabled = True
        self.filtered_media = None
        self.current_media = None
        self.poster_index = 0
        self.poster_filenames = []
        self.poster_layer.clear()
        self.poster_pixmap = QPixmap()
        self.hide_card_elements()

    def hide_card_elements(self):
        self.btn_info.hide()
        self.poster_layer.clear()
        self.poster_pixmap = QPixmap()
        self.overlay_layer.hide()

    def show_card_elements(self):
        self.btn_info.show()

    def has_visible_media(self):
        return not self.is_disabled and self.current_media is not None

    def get_current_media_key(self):
        return get_media_key(self.current_media)

    def _get_media_key(self):
        return get_media_key(self.current_media)

    def _save_current_poster_index(self):
        media_key = self._get_media_key()
        if media_key is not None:
            self.poster_index_by_media_key[media_key] = self.poster_index

    def _poster_path(self, filename):
        return POSTER_DIR / filename.lstrip("/")

    def _render_poster(self):
        if self.poster_pixmap.isNull() or self.poster_layer.size().isEmpty():
            self.poster_layer.clear()
            return
        self.poster_layer.setPixmap(
            self.poster_pixmap.scaled(
                self.poster_layer.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _layout_buttons(self):
        self.btn_info.move(MEDIA_CARD_BUTTON_MARGIN, MEDIA_CARD_BUTTON_MARGIN)

    def _request_drag(self, hotspot):
        if self.drag_enabled and not self.is_disabled:
            self.drag_requested.emit(self, hotspot)

    def show_card(self):
        if not self.is_disabled:
            self.overlay_layer.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.poster_layer.setGeometry(self.rect())
        self.overlay_layer.setGeometry(self.rect())
        self._render_poster()
        self._layout_buttons()

    def enterEvent(self, event):
        if not self.is_disabled:
            self.overlay_layer.show()
            self.overlay_layer.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.is_disabled:
            self.overlay_layer.hide()
        super().leaveEvent(event)
