from app.media_card_info_panel import MediaCardInfoPanel

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

class MediaCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.is_disabled = True
        self.is_hidden = False #substituir a check do pix por isso aqui
        self.is_pinned = False

        self.filtered_media = None
        self.current_media = None
        self.media_index_history = []
        self.current_index_in_history = -1

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
        self.pin_layer = QLabel(self)
        self.pin_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_layer.setScaledContents(True)

        # layer 3 – interaction overlay
        self.overlay_layer = MediaCardOverlay(self)
        self.overlay_layer.hide()

        self.btn_info = self.make_button("app/assets/media_card_icons/info.png", self.overlay_layer)
        self.btn_close = self.make_button("app/assets/media_card_icons/close.png", self.overlay_layer)
        self.btn_previous = self.make_button("app/assets/media_card_icons/prev.png", self.overlay_layer)
        self.btn_next = self.make_button("app/assets/media_card_icons/next.png", self.overlay_layer)
        self.btn_pin = self.make_button("app/assets/media_card_icons/pin.png", self.overlay_layer, size=(140, 42))

        # layer 4 – info panel
        self.info_panel = MediaCardInfoPanel(self)
        self.info_panel.hide()

        # main card clicks
        self.overlay_layer.background_clicked.connect(self.on_overlay_clicked)
        self.btn_info.clicked.connect(self.on_info_clicked)
        self.btn_close.clicked.connect(self.on_close_clicked)
        self.btn_previous.clicked.connect(self.on_previous_clicked)
        self.btn_next.clicked.connect(self.on_next_clicked)
        self.btn_pin.clicked.connect(self.on_pin_clicked)

        # info panel clicks
        self.info_panel.edit_clicked.connect(self.show_edit_window)
        self.info_panel.back_clicked.connect(self.hide_info_panel)

        # set layer order
        self.poster_layer.lower()
        #self.poster_correction_layer.raise_()
        self.pin_layer.raise_()
        self.overlay_layer.raise_()
        self.info_panel.raise_()

    def make_button(self, icon_img_path, parent, size=(42, 42)):
        btn = QToolButton(parent)
        btn.setFixedSize(size[0], size[1])
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

    def init_card_session(self, filtered_media):
        self.is_disabled = False
        self.filtered_media = filtered_media
        self.load_next_media()

    def load_next_media(self):
        if self.current_index_in_history + 1 == len(self.media_index_history):
            next_media_index = self.filtered_media.next_media_index
            self.media_index_history.append(next_media_index)
            self.current_index_in_history += 1

            media_list = self.filtered_media.media_list
            self.filtered_media.next_media_index = (self.filtered_media.next_media_index + 1) % len(media_list)

        else:
            self.current_index_in_history += 1
            next_media_index = self.media_index_history[self.current_index_in_history]

        self.load_card_at_index(next_media_index)

    def load_previous_media(self):
        if self.current_index_in_history <= 0 and not self.poster_pixmap.isNull():
            return

        if not self.poster_pixmap.isNull():
            self.current_index_in_history -= 1

        previous_media_index = self.media_index_history[self.current_index_in_history]
        self.load_card_at_index(previous_media_index)

    def load_card_at_index(self, filtered_media_index):
        self.current_media = self.filtered_media.media_list[filtered_media_index]

        # set poster image
        self.update_poster_image()

        # set info panel
        poster_slots = [self.info_panel.poster_1, self.info_panel.poster_2, self.info_panel.poster_3]
        media_posters = self.current_media["posters"]

        for i, poster_slot in enumerate(poster_slots):
            if i < len(media_posters):
                pixmap = QPixmap("data/media_posters/" + media_posters[i])
                poster_slot.setPixmap(pixmap)
            else:
                poster_slot.clear()

        self.info_panel.title_value.setText(self.current_media["title"])
        self.info_panel.year_value.setText(self.current_media["year"])
        self.info_panel.duration_value.setText(self.current_media["duration"])
        self.info_panel.status_value.setText(self.current_media["status"])
        if self.current_media["rating"]:
            self.info_panel.rating_label.show()
            self.info_panel.rating_value.setText(self.current_media["rating"])
        else:
            self.info_panel.rating_label.hide()
            self.info_panel.rating_value.clear()
        self.info_panel.streaming_value.setText(self.current_media["streaming_at"])

        #media_list = self.filtered_media.media_list
        #current_index = self.filtered_media.next_media_index
        #self.filtered_media.next_media_index = (current_index + 1) % len(media_list)

    def update_poster_image(self):
        poster_index = self.current_media["poster_index"]
        poster_filename = self.current_media["posters"][poster_index]
        poster_path = "data/media_posters/" + poster_filename

        self.poster_pixmap = load_pixmap_with_red_fix(poster_path, 0.9)
        #self.poster_pixmap = QPixmap("images/posters/" + poster_filename)
        self.poster_layer.setPixmap(
           self.poster_pixmap.scaledToWidth(
               self.width(),
               Qt.TransformationMode.SmoothTransformation
           )
        )

    def on_overlay_clicked(self):
        print("overlay clicked")
        if self.poster_pixmap.isNull():
            return

        posters = self.current_media["posters"]
        current_index = self.current_media["poster_index"]
        self.current_media["poster_index"] = (current_index + 1) % len(posters)

        self.update_poster_image()

    def on_info_clicked(self):
        print("info clicked")
        self.info_panel.show()
        self.info_panel.raise_()
        self.overlay_layer.hide()

    def on_close_clicked(self):
        self.clear_pinned()
        self.hide_card_elements()

    def on_previous_clicked(self):
        self.clear_pinned()
        self.show_card_elements()
        self.load_previous_media()

    def on_next_clicked(self):
        self.clear_pinned()
        self.show_card_elements()
        self.load_next_media()

    def clear_pinned(self):
        self.is_pinned = False
        self.update_pin_status()

    def on_pin_clicked(self):
        self.is_pinned = not self.is_pinned
        self.update_pin_status()

    def update_pin_status(self):
        if self.is_pinned:
            self.btn_pin.setIcon(QIcon("app/assets/media_card_icons/unpin.png"))
            pixmap = QPixmap("app/assets/pinned_overlay.png")
            if pixmap.isNull():
                self.pin_layer.clear()
                return
            self.pin_layer.setPixmap(pixmap)

        else:
            self.btn_pin.setIcon(QIcon("app/assets/media_card_icons/pin.png"))
            self.pin_layer.clear()

    def show_edit_window(self):
        pass #opens edit window over main window

    def hide_info_panel(self):
        self.info_panel.hide()

        if self.underMouse():
            self.overlay_layer.show()
            self.overlay_layer.raise_()

    def hide_card_elements(self):
        self.btn_info.hide()
        self.btn_close.hide()
        self.btn_pin.hide()
        self.poster_layer.clear()
        self.poster_pixmap = QPixmap()

    def show_card_elements(self):
        self.btn_info.show()
        self.btn_close.show()
        self.btn_pin.show()

    def show_card(self):
        self.overlay_layer.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        rect = self.rect()

        self.poster_layer.setGeometry(rect)

        # if not self.poster_pixmap.isNull():
        #     scaled = self.poster_pixmap.scaled(
        #         self.poster_layer.size(),
        #         Qt.AspectRatioMode.KeepAspectRatio,
        #         Qt.TransformationMode.SmoothTransformation
        #     )
        #
        #     self.poster_layer.setPixmap(scaled)
        #     self.poster_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not self.poster_pixmap.isNull():
           scaled = self.poster_pixmap.scaledToWidth(
               self.poster_layer.width(),
               Qt.TransformationMode.SmoothTransformation
           )
           self.poster_layer.setPixmap(scaled)

        #self.poster_correction_layer.setGeometry(rect)
        self.pin_layer.setGeometry(rect)
        self.overlay_layer.setGeometry(rect)
        self.info_panel.setGeometry(rect)

        margin = 6
        w = self.btn_info.width()
        h = self.btn_info.height()

        self.btn_info.move(margin, margin)
        self.btn_close.move(rect.width() - w - margin, margin)

        self.btn_previous.move(margin, rect.height() - h - margin)
        self.btn_next.move(rect.width() - w - margin, rect.height() - h - margin)

        print("#5")
        pin_x = (rect.width() - self.btn_pin.width()) // 2
        pin_y = rect.height() - self.btn_pin.height() - margin
        self.btn_pin.move(pin_x, pin_y)

    def enterEvent(self, event):
        if not self.info_panel.isVisible() and not self.is_disabled:
            self.overlay_layer.show()
            self.overlay_layer.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.info_panel.isVisible():
            self.overlay_layer.hide()
        super().leaveEvent(event)


#def fill_media_card(media_card, media_card_infos):
#    posters = media_card_infos.get("posters", [])
#
#    if posters:
#        media_card.set_posters(posters)
#    else:
#        media_card.set_posters(["images/posters/elio-1.jpg"])