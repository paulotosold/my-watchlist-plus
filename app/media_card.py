from app.media_card_info_panel import MediaCardInfoPanel
from app.config import SUBSCRIBED_FLATRATE_PROVIDER_NAMES
from app.media_state_controls import NONE_WATCH_STATE_LABEL

from copy import deepcopy
from pathlib import Path
import random

from PIL import Image
import numpy as np

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QIcon, QImage, QPainter, QColor
from PySide6.QtWidgets import (
    QLabel,
    QWidget,
    QFrame,
    QToolButton,
    QGraphicsOpacityEffect,
)


class MediaCardOverlay(QWidget):
    background_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is None:
                self.background_clicked.emit()

        super().mousePressEvent(event)

def load_pixmap_with_red_fix(path, strength=0.85):
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32)

    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]

    mask = (r > g) & (r > b)
    r[mask] *= strength

    arr[:,:,0] = r

    arr = np.clip(arr, 0, 255).astype(np.uint8)

    h, w, ch = arr.shape

    qimg = QImage(
        arr.data,
        w,
        h,
        ch * w,
        QImage.Format.Format_RGB888
    ).copy()

    return QPixmap.fromImage(qimg)

class ColorCorrectionLayer(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # equivalente ao #00C8FF com ~10%
        self.tint = QColor(0, 200, 255, int(255 * 0.10))

        self.mode = QPainter.CompositionMode.CompositionMode_SourceOver

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.setCompositionMode(self.mode)
        painter.fillRect(self.rect(), self.tint)

def get_media_key(media_draft):
    if not media_draft:
        return None

    return media_draft.get("media_id")

class MediaCard(QFrame):
    BASE_CARD_WIDTH = 269
    BASE_SQUARE_BUTTON_SIZE = 42
    BASE_PIN_BUTTON_WIDTH = 140
    BASE_PIN_BUTTON_HEIGHT = 42
    BASE_MARGIN = 6
    MINIMUM_HITBOX_SIZE = 24

    state_changed = Signal()
    details_requested = Signal(object)
    dismiss_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.is_disabled = True
        self.is_pinned = False

        self.filtered_media = None
        self.current_media = None
        self.poster_index = 0
        self.poster_filenames = []
        self.poster_index_by_media_key = {}

        # layer 1 – poster
        self.poster_pixmap = QPixmap()
        self.poster_layer = QLabel(self)
        self.poster_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_layer.setStyleSheet("background-color: white;")

        # layer 1.5 – poster color correction
        #self.poster_correction_layer = ColorCorrectionLayer(self)
        #self.poster_correction_layer = QLabel(self)
        #self.poster_correction_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # cinza translúcido para “matar” um pouco a saturação
        #self.poster_correction_layer.setStyleSheet("background-color: rgba(0, 180, 255, 22);")

        # deixa a layer invisível para mouse, importante se tiver interação
        #self.poster_correction_layer.setAttribute(
        #    Qt.WidgetAttribute.WA_TransparentForMouseEvents,
        #    True
        #)

        # layer 2 – decorative overlay displayed when pinned
        self.pin_pixmap = QPixmap("app/assets/pinned_overlay.png")
        self.pin_layer = QLabel(self)
        self.pin_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_layer.setScaledContents(False)

        # layer 3 – interaction overlay
        self.overlay_layer = MediaCardOverlay(self)
        self.overlay_layer.hide()

        square_button_size = (
            self.BASE_SQUARE_BUTTON_SIZE,
            self.BASE_SQUARE_BUTTON_SIZE,
        )
        self.btn_info = self.make_button(
            "app/assets/media_card_icons/info.png",
            self.overlay_layer,
            size=square_button_size,
        )
        self.btn_close = self.make_button(
            "app/assets/media_card_icons/close.png",
            self.overlay_layer,
            size=square_button_size,
        )
        self.btn_pin = self.make_button(
            "app/assets/media_card_icons/pin.png",
            self.overlay_layer,
            size=(self.BASE_PIN_BUTTON_WIDTH, self.BASE_PIN_BUTTON_HEIGHT),
        )

        # layer 4 – info panel
        self.info_panel = MediaCardInfoPanel(self)
        self.info_panel.hide()

        # main card clicks
        self.overlay_layer.background_clicked.connect(self.on_overlay_clicked)
        self.btn_info.clicked.connect(self.request_details)
        self.btn_close.clicked.connect(self.on_close_clicked)
        self.btn_pin.clicked.connect(self.on_pin_clicked)

        # info panel clicks
        self.info_panel.details_clicked.connect(self.request_details)
        self.info_panel.back_clicked.connect(self.hide_info_panel)

        # set layer order
        self.poster_layer.lower()
        #self.poster_correction_layer.raise_()
        self.pin_layer.raise_()
        self.overlay_layer.raise_()
        self.info_panel.raise_()

    def make_button(self, icon_img_path, parent, size=(42, 42)):
        btn = QToolButton(parent)
        btn.base_icon_size = QSize(*size)
        btn.setFixedSize(
            max(self.MINIMUM_HITBOX_SIZE, size[0]),
            max(self.MINIMUM_HITBOX_SIZE, size[1]),
        )
        btn.setIcon(QIcon(icon_img_path))
        btn.setIconSize(QSize(size[0], size[1]))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QToolButton {
                background: transparent;
               border: none;
                padding: 0px;
            }
        """)

        opacity = QGraphicsOpacityEffect(btn)
        opacity.setOpacity(0.9)
        btn.setGraphicsEffect(opacity)

        return btn

    def set_filtered_media(self, filtered_media):
        self.filtered_media = filtered_media

    def init_card_session(self, filtered_media, media_draft=None):
        self.filtered_media = filtered_media
        self.poster_index = 0
        self.poster_filenames = []
        self.info_panel.hide()

        if media_draft is None:
            self.clear_card()
            self.filtered_media = filtered_media
            return

        self.is_disabled = False
        self.show_card_elements()
        self.load_card_media(media_draft)

    def load_card_media(self, media_draft):
        self.current_media = deepcopy(media_draft)
        self.poster_filenames = self._get_poster_filenames()
        self.poster_index = self._get_initial_poster_index()
        self._save_current_poster_index()
        self.show_card_elements()
        self.info_panel.hide()

        # set poster image
        self.update_poster_image()

        info_panel_poster = self._get_info_panel_poster_filename()

        if info_panel_poster:
            self._set_info_panel_poster_image(info_panel_poster)
        else:
            self._clear_info_panel_poster_image()

        self.info_panel.title_value.setText(self._get_title())
        self.info_panel.year_value.setText(self._get_year())
        self.info_panel.duration_value.setText(self._get_duration())
        self.info_panel.status_value.setText(self._get_watch_state())

        impression = self._get_impression()
        if impression:
            self.info_panel.impression_label.show()
            self.info_panel.impression_value.setText(impression)
        else:
            self.info_panel.impression_label.hide()
            self.info_panel.impression_value.clear()

        streaming_label, streaming_value, has_streaming = self._get_subscription_streaming_info()
        self.info_panel.set_streaming_info(streaming_label, streaming_value, has_streaming)

    def update_poster_image(self):
        if not self.poster_filenames:
            self.poster_layer.clear()
            self.poster_pixmap = QPixmap()
            return

        poster_filename = self.poster_filenames[self.poster_index]
        poster_path = self._poster_path(poster_filename)

        try:
            self.poster_pixmap = load_pixmap_with_red_fix(poster_path, 0.9)
        except (FileNotFoundError, OSError):
            self.poster_layer.clear()
            self.poster_pixmap = QPixmap()
            return

        self._render_poster()

    def on_overlay_clicked(self):
        if self.poster_pixmap.isNull():
            return

        if not self.poster_filenames:
            return

        self.poster_index = (self.poster_index + 1) % len(self.poster_filenames)
        self._save_current_poster_index()

        self.update_poster_image()

    def on_close_clicked(self):
        self.clear_pinned()
        self.dismiss_requested.emit()

    def clear_pinned(self):
        self.is_pinned = False
        self.update_pin_status()

    def on_pin_clicked(self):
        self.is_pinned = not self.is_pinned
        self.update_pin_status()
        self.state_changed.emit()

    def update_pin_status(self):
        if self.is_pinned:
            self.btn_pin.setIcon(QIcon("app/assets/media_card_icons/unpin.png"))
            if self.pin_pixmap.isNull():
                self.pin_layer.clear()
                return
            self._render_pin_overlay()

        else:
            self.btn_pin.setIcon(QIcon("app/assets/media_card_icons/pin.png"))
            self.pin_layer.clear()

    def request_details(self):
        if self.current_media is None:
            return

        self.details_requested.emit(deepcopy(self.current_media))

    def show_details_window(self):
        self.request_details()

    def hide_info_panel(self):
        self.info_panel.hide()

        if self.underMouse() and not self.is_disabled:
            self.overlay_layer.show()
            self.overlay_layer.raise_()

    def hide_card_elements(self):
        self.btn_info.hide()
        self.btn_close.hide()
        self.btn_pin.hide()
        self.info_panel.hide()
        self.poster_layer.clear()
        self.poster_pixmap = QPixmap()
        self.overlay_layer.hide()

    def show_card_elements(self):
        self.btn_info.show()
        self.btn_close.show()
        self.btn_pin.show()

    def clear_card(self):
        self.is_disabled = True
        self.is_pinned = False
        self.filtered_media = None
        self.current_media = None
        self.poster_index = 0
        self.poster_filenames = []
        self.pin_layer.clear()
        self.update_pin_status()
        self.hide_card_elements()
        self.overlay_layer.hide()

    def has_visible_media(self):
        return not self.is_disabled and self.current_media is not None

    def get_current_media_key(self):
        return get_media_key(self.current_media)

    def _get_metadata(self):
        return self.current_media.get("metadata", {}) if self.current_media else {}

    def _get_series_summary(self):
        series_view = (
            self.current_media.get("series_view")
            if self.current_media
            else None
        )
        return (series_view or {}).get("summary") or {}

    def _get_user_data(self):
        return self.current_media.get("user_data", {}) if self.current_media else {}

    def _get_title(self):
        return self._get_metadata().get("title") or "Untitled"

    def _get_year(self):
        metadata = self._get_metadata()
        release_date = metadata.get("release_date")

        if not release_date and metadata.get("media_type") == "series":
            series_summary = self._get_series_summary()
            release_date = series_summary.get("first_air_date")

        if not release_date:
            return ""

        return str(release_date)[:4]

    def _get_duration(self):
        metadata = self._get_metadata()

        if metadata.get("media_type") == "series":
            series_summary = self._get_series_summary()
            episode_count = series_summary.get("episode_count")

            if episode_count in (None, "", 0):
                return ""

            return f"{episode_count} eps"

        runtime_min = metadata.get("runtime_min")

        if runtime_min in (None, "", 0):
            return ""

        return f"{runtime_min} min"

    def _get_watch_state(self):
        watch_state = self._get_user_data().get("watch_state")

        if watch_state is None:
            return NONE_WATCH_STATE_LABEL

        return str(watch_state).replace("_", " ").title()

    def _get_impression(self):
        impression = self._get_user_data().get("impression")

        if impression is None:
            return ""

        return str(impression).replace("_", " ")

    def _get_subscription_streaming_info(self):
        providers = self.current_media.get("watch_providers", []) if self.current_media else []
        subscribed_provider_names = {
            provider_name.strip().casefold()
            for provider_name in SUBSCRIBED_FLATRATE_PROVIDER_NAMES
        }
        matched_provider_names = []
        seen = set()

        for provider in providers:
            provider_name = provider.get("provider_name")

            if provider.get("access_type") != "flatrate" or not provider_name:
                continue

            normalized_name = provider_name.strip().casefold()

            if normalized_name not in subscribed_provider_names or normalized_name in seen:
                continue

            matched_provider_names.append(provider_name)
            seen.add(normalized_name)

        if matched_provider_names:
            return "Streaming for you:", ", ".join(matched_provider_names), True

        return "", "Not in your subscriptions", False

    def _get_poster_filenames(self):
        posters = self.current_media.get("posters", []) if self.current_media else []
        filenames = []
        seen = set()

        for poster in posters:
            if poster.get("curation_status") not in {"selected", "pending"}:
                continue

            filename = poster.get("filename")

            if not filename or filename in seen:
                continue

            if not self._poster_path(filename).exists():
                continue

            filenames.append(filename)
            seen.add(filename)

        return filenames

    def _get_initial_poster_index(self):
        if not self.poster_filenames:
            return 0

        saved_index = self.poster_index_by_media_key.get(self._get_media_key())

        if saved_index is not None:
            return min(saved_index, len(self.poster_filenames) - 1)

        return random.randrange(len(self.poster_filenames))

    def _get_info_panel_poster_filename(self):
        posters = self.current_media.get("posters", []) if self.current_media else []
        first_filename = None

        for poster in posters:
            if poster.get("curation_status") not in {"selected", "pending"}:
                continue

            filename = poster.get("filename")

            if not filename or not self._poster_path(filename).exists():
                continue

            if first_filename is None:
                first_filename = filename

            if poster.get("is_default"):
                return filename

        return first_filename

    def _set_info_panel_poster_image(self, filename):
        pixmap = QPixmap(str(self._poster_path(filename)))

        if pixmap.isNull():
            self._clear_info_panel_poster_image()
            return

        scaled_pixmap = pixmap.scaledToHeight(
            140,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.info_panel.poster_image.setFixedSize(scaled_pixmap.size())
        self.info_panel.poster_image.setPixmap(scaled_pixmap)

    def _clear_info_panel_poster_image(self):
        self.info_panel.poster_image.clear()
        self.info_panel.poster_image.setFixedSize(94, 140)

    def _save_current_poster_index(self):
        media_key = self._get_media_key()

        if media_key is None:
            return

        self.poster_index_by_media_key[media_key] = self.poster_index

    def _get_media_key(self):
        return get_media_key(self.current_media)

    def _poster_path(self, filename):
        return Path("data/media_posters") / filename.lstrip("/")

    def _render_poster(self):
        if self.poster_pixmap.isNull() or self.poster_layer.size().isEmpty():
            self.poster_layer.clear()
            return

        scaled_pixmap = self.poster_pixmap.scaled(
            self.poster_layer.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.poster_layer.setPixmap(scaled_pixmap)

    def _render_pin_overlay(self):
        if (
            not self.is_pinned
            or self.pin_pixmap.isNull()
            or self.pin_layer.size().isEmpty()
        ):
            self.pin_layer.clear()
            return

        scaled_pixmap = self.pin_pixmap.scaled(
            self.pin_layer.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.pin_layer.setPixmap(scaled_pixmap)

    def _scale_button(self, button, scale_factor):
        base_size = button.base_icon_size
        icon_width = max(1, round(base_size.width() * scale_factor))
        icon_height = max(1, round(base_size.height() * scale_factor))
        hitbox_width = max(self.MINIMUM_HITBOX_SIZE, icon_width)
        hitbox_height = max(self.MINIMUM_HITBOX_SIZE, icon_height)

        button.setFixedSize(hitbox_width, hitbox_height)
        button.setIconSize(QSize(icon_width, icon_height))

    def _layout_buttons(self):
        card_width = self.width()
        card_height = self.height()
        scale_factor = card_width / self.BASE_CARD_WIDTH
        margin = max(0, round(self.BASE_MARGIN * scale_factor))

        for button in (self.btn_info, self.btn_close, self.btn_pin):
            self._scale_button(button, scale_factor)

        self.btn_info.move(margin, margin)
        self.btn_close.move(
            card_width - self.btn_close.width() - margin,
            margin,
        )

        pin_x = (card_width - self.btn_pin.width()) // 2
        pin_y = card_height - self.btn_pin.height() - margin
        self.btn_pin.move(pin_x, pin_y)

    def show_card(self):
        if self.is_disabled:
            return

        self.overlay_layer.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        rect = self.rect()

        self.poster_layer.setGeometry(rect)
        self.pin_layer.setGeometry(rect)
        self.overlay_layer.setGeometry(rect)
        self.info_panel.setGeometry(rect)

        self._render_poster()
        self._render_pin_overlay()
        self._layout_buttons()

    def enterEvent(self, event):
        if not self.info_panel.isVisible() and not self.is_disabled:
            self.overlay_layer.show()
            self.overlay_layer.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.info_panel.isVisible() and not self.is_disabled:
            self.overlay_layer.hide()
        super().leaveEvent(event)


#def fill_media_card(media_card, media_card_infos):
#    posters = media_card_infos.get("posters", [])
#
#    if posters:
#        media_card.set_posters(posters)
#    else:
#        media_card.set_posters(["images/posters/elio-1.jpg"])
