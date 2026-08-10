from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy


CLICKABLE_ENTRY_LABEL_HEIGHT = 20


class ClickableEntryLabel(QLabel):
    activated = Signal()

    def __init__(self, text, parent=None, callback=None):
        super().__init__(text or "", parent)

        self._press_position = None
        self._press_started_over_text = False
        self._pointer_over_text = False
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.setWordWrap(False)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setFixedHeight(CLICKABLE_ENTRY_LABEL_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumWidth(0)

        if callback is not None:
            self.activated.connect(callback)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._update_pointer_state(event.position().toPoint())

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_pointer_over_text(False)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._update_pointer_state(event.position().toPoint())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
            self._press_started_over_text = self._is_over_rendered_text(
                self._press_position
            )

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        release_position = event.position().toPoint()
        should_activate = (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_position is not None
            and self._press_started_over_text
            and self._is_over_rendered_text(release_position)
            and (
                release_position - self._press_position
            ).manhattanLength() < QApplication.startDragDistance()
        )

        super().mouseReleaseEvent(event)
        self._press_position = None
        self._press_started_over_text = False

        if should_activate and not self.hasSelectedText():
            self.activated.emit()

    def keyPressEvent(self, event):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            event.accept()
            self.activated.emit()
            return

        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._refresh_underline()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._refresh_underline()

    def _update_pointer_state(self, position):
        self._set_pointer_over_text(self._is_over_rendered_text(position))

    def _set_pointer_over_text(self, is_over_text):
        if self._pointer_over_text == is_over_text:
            return

        self._pointer_over_text = is_over_text

        if is_over_text:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()

        self._refresh_underline()

    def _refresh_underline(self):
        font = self.font()
        font.setUnderline(self._pointer_over_text or self.hasFocus())
        self.setFont(font)

    def _is_over_rendered_text(self, position):
        text = self.text()

        if not text:
            return False

        content_rect = self.contentsRect()
        metrics = self.fontMetrics()
        text_width = min(metrics.horizontalAdvance(text), content_rect.width())
        text_height = min(metrics.height(), content_rect.height())
        text_top = content_rect.top() + max(
            0,
            (content_rect.height() - text_height) // 2,
        )

        return (
            content_rect.left() <= position.x() < content_rect.left() + text_width
            and text_top <= position.y() < text_top + text_height
        )
