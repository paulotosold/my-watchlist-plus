from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QFrame, QLabel, QScrollArea, QSizePolicy,
)

from app.ui.styles import ENTRY_LABEL_STYLE


class HistoryCaption(QScrollArea):
    """A single-line action with hidden horizontal scrolling and drag support."""

    activated = Signal()
    metrics_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press_position = None
        self._press_scroll = 0
        self._dragged = False
        self._hovered = False
        self._reported_height = None
        self._font_change_timer = QTimer(self)
        self._font_change_timer.setSingleShot(True)
        self._font_change_timer.timeout.connect(self._update_font_metrics)
        self.setObjectName("historyCaption")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(False)
        self.setStyleSheet(
            "QScrollArea#historyCaption { border: none; background: white; }"
            "QLabel {" + ENTRY_LABEL_STYLE + "}"
        )
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(False)
        # Stylesheet padding gives QLabel a frame width, which otherwise enables
        # its implicit text indent and clips the tail of a tightly sized label.
        self.label.setIndent(0)
        self.label.setContentsMargins(4, 0, 4, 0)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.installEventFilter(self)
        self.setWidget(self.label)
        self.label.ensurePolished()

    def caption_height(self):
        return max(24, self.label.fontMetrics().height() + 8)

    def set_text(self, text):
        if text != self.label.text():
            self.label.setText(text)
            self.horizontalScrollBar().setValue(0)
        self.setAccessibleName(text)
        self._update_content()

    def _update_content(self):
        if not hasattr(self, "label"):
            return
        available = self.viewport().width()
        text_width = self.label.sizeHint().width()
        overflowing = text_width > available
        self.label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter
            | (Qt.AlignmentFlag.AlignLeft if overflowing else Qt.AlignmentFlag.AlignHCenter)
        )
        self.label.resize(max(available, text_width), self.viewport().height())
        if not overflowing:
            self.horizontalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_content()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FontChange:
            # QLabel invalidates its cached sizeHint after this event filter.
            self._font_change_timer.start(0)
        return super().eventFilter(watched, event)

    def _update_font_metrics(self):
        self._update_content()
        height = self.caption_height()
        if height != self._reported_height:
            self._reported_height = height
            self.metrics_changed.emit()

    def wheelEvent(self, event):
        pixel = event.pixelDelta()
        angle = event.angleDelta()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        movement = pixel if not pixel.isNull() else angle
        horizontal = shift or abs(movement.x()) > abs(movement.y())
        delta = (movement.x() or movement.y()) if horizontal else 0
        if pixel.isNull():
            delta = delta / 120 * 40
        if delta and self.horizontalScrollBar().maximum() > 0:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - round(delta))
            event.accept()
        else:
            self._forward_wheel_to_parent(event)

    def _forward_wheel_to_parent(self, event):
        # Nested scroll areas stop implicit wheel propagation on some platforms.
        # Forward to the enclosing viewport explicitly, retaining native deltas.
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is None:
            event.ignore()
            return
        viewport = parent.viewport()
        forwarded = QWheelEvent(
            viewport.mapFromGlobal(event.globalPosition().toPoint()),
            event.globalPosition(), event.pixelDelta(), event.angleDelta(),
            event.buttons(), event.modifiers(), event.phase(), event.inverted(),
            event.source(), event.pointingDevice(),
        )
        QApplication.sendEvent(viewport, forwarded)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._press_position = event.position().toPoint()
            self._press_scroll = self.horizontalScrollBar().value()
            self._dragged = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_position is not None:
            distance = event.position().toPoint() - self._press_position
            if distance.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.horizontalScrollBar().setValue(self._press_scroll - distance.x())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_position is not None:
            distance = event.position().toPoint() - self._press_position
            activate = (
                not self._dragged
                and distance.manhattanLength() < QApplication.startDragDistance()
                and self.viewport().rect().contains(event.position().toPoint())
            )
            self._press_position = None
            event.accept()
            if activate:
                self.activated.emit()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            event.accept()
            self.activated.emit()
        else:
            super().keyPressEvent(event)

    def _update_underline(self):
        font = self.label.font()
        underline = self._hovered or self.hasFocus()
        if font.underline() != underline:
            font.setUnderline(underline)
            self.label.setFont(font)
        self.viewport().update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hovered = True
        self._update_underline()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hovered = False
        self._update_underline()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._update_underline()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._update_underline()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.hasFocus():
            painter = QPainter(self.viewport())
            painter.setPen(QPen(Qt.GlobalColor.darkGray, 1, Qt.PenStyle.DotLine))
            painter.drawRect(self.viewport().rect().adjusted(1, 1, -2, -2))
