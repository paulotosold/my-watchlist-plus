from copy import deepcopy
from functools import lru_cache
import random

from PIL import Image
import numpy as np

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QLabel,
    QWidget,
    QFrame,
    QToolButton,
    QGraphicsOpacityEffect,
)

from app.paths import ASSETS_DIR, MEDIA_POSTERS_DIR


MEDIA_CARD_ICON_HEIGHT = 32
MEDIA_CARD_BUTTON_MARGIN = 6

MEDIA_CARD_ICON_DIR = ASSETS_DIR / "media_card_icons"
POSTER_DIR = MEDIA_POSTERS_DIR


@lru_cache(maxsize=None)
def _icon_dimensions_for_height(icon_img_path, icon_height):
    source_size = QImageReader(str(icon_img_path)).size()

    if (
        not source_size.isValid()
        or source_size.width() <= 0
        or source_size.height() <= 0
    ):
        return icon_height, icon_height

    icon_width = max(
        1,
        round(
            icon_height
            * source_size.width()
            / source_size.height()
        ),
    )
    return icon_width, icon_height


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
        self.pin_pixmap = QPixmap(str(ASSETS_DIR / "pinned_overlay.png"))
        self.pin_layer = QLabel(self)
        self.pin_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_layer.setScaledContents(False)

        # layer 3 – interaction overlay
        self.overlay_layer = MediaCardOverlay(self)
        self.overlay_layer.hide()

        self.btn_info = self.make_button(
            MEDIA_CARD_ICON_DIR / "info.png",
            self.overlay_layer,
        )
        self.btn_close = self.make_button(
            MEDIA_CARD_ICON_DIR / "close.png",
            self.overlay_layer,
        )
        self.btn_pin = self.make_button(
            MEDIA_CARD_ICON_DIR / "pin.png",
            self.overlay_layer,
        )

        # main card clicks
        self.overlay_layer.background_clicked.connect(self.on_overlay_clicked)
        self.btn_info.clicked.connect(self.request_details)
        self.btn_close.clicked.connect(self.on_close_clicked)
        self.btn_pin.clicked.connect(self.on_pin_clicked)

        # set layer order
        self.poster_layer.lower()
        #self.poster_correction_layer.raise_()
        self.pin_layer.raise_()
        self.overlay_layer.raise_()

    def make_button(self, icon_img_path, parent):
        btn = QToolButton(parent)
        icon_size = QSize(
            *_icon_dimensions_for_height(
                icon_img_path,
                MEDIA_CARD_ICON_HEIGHT,
            )
        )
        btn.setFixedSize(icon_size)
        btn.setIcon(QIcon(str(icon_img_path)))
        btn.setIconSize(icon_size)
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

        self.update_poster_image()

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
            self.btn_pin.setIcon(
                QIcon(str(MEDIA_CARD_ICON_DIR / "unpin.png"))
            )
            if self.pin_pixmap.isNull():
                self.pin_layer.clear()
                return
            self._render_pin_overlay()

        else:
            self.btn_pin.setIcon(
                QIcon(str(MEDIA_CARD_ICON_DIR / "pin.png"))
            )
            self.pin_layer.clear()

    def request_details(self):
        if self.current_media is None:
            return

        self.details_requested.emit(deepcopy(self.current_media))

    def show_details_window(self):
        self.request_details()

    def hide_card_elements(self):
        self.btn_info.hide()
        self.btn_close.hide()
        self.btn_pin.hide()
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

    def _save_current_poster_index(self):
        media_key = self._get_media_key()

        if media_key is None:
            return

        self.poster_index_by_media_key[media_key] = self.poster_index

    def _get_media_key(self):
        return get_media_key(self.current_media)

    def _poster_path(self, filename):
        return POSTER_DIR / filename.lstrip("/")

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

    def _layout_buttons(self):
        card_width = self.width()
        card_height = self.height()

        self.btn_info.move(
            MEDIA_CARD_BUTTON_MARGIN,
            MEDIA_CARD_BUTTON_MARGIN,
        )
        self.btn_close.move(
            card_width
            - self.btn_close.width()
            - MEDIA_CARD_BUTTON_MARGIN,
            MEDIA_CARD_BUTTON_MARGIN,
        )

        pin_x = (card_width - self.btn_pin.width()) // 2
        pin_y = (
            card_height
            - self.btn_pin.height()
            - MEDIA_CARD_BUTTON_MARGIN
        )
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

        self._render_poster()
        self._render_pin_overlay()
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


#def fill_media_card(media_card, media_card_infos):
#    posters = media_card_infos.get("posters", [])
#
#    if posters:
#        media_card.set_posters(posters)
#    else:
#        media_card.set_posters(["images/posters/elio-1.jpg"])
