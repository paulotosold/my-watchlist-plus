from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    DETAIL_ICON_BUTTON_SIZE,
    DETAIL_ICON_DIR,
    DETAIL_ICON_SIZE,
)


DETAIL_HEADER_ICON_TEXT_SPACING = 1
DETAIL_ICON_BUTTON_RADIUS = DETAIL_ICON_BUTTON_SIZE // 2
DETAIL_ICON_BUTTON_HOVER_SIZE = DETAIL_ICON_BUTTON_SIZE + 4
DETAIL_ICON_BUTTON_HOVER_RADIUS = DETAIL_ICON_BUTTON_HOVER_SIZE // 2
DETAIL_ICON_BUTTON_HOVER_BACKGROUND = "rgba(0, 0, 0, 18)"
DETAIL_ICON_BUTTON_STYLE = f"""
QToolButton {{
    background: transparent;
    border: none;
    border-radius: {DETAIL_ICON_BUTTON_RADIUS}px;
    padding: 0;
}}
QToolButton:disabled {{
    background: transparent;
    border: none;
}}
"""
DETAIL_ICON_BUTTON_HOVER_STYLE = f"""
background: {DETAIL_ICON_BUTTON_HOVER_BACKGROUND};
border: none;
border-radius: {DETAIL_ICON_BUTTON_HOVER_RADIUS}px;
"""


class DetailIconButton(QToolButton):
    """Icon button whose hover circle can exceed its layout footprint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_circle = None

    def enterEvent(self, event):
        self._set_hover_circle_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hover_circle_visible(False)
        super().leaveEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._position_hover_circle()

    def hideEvent(self, event):
        self._set_hover_circle_visible(False)
        super().hideEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)

        if (
            event.type() == QEvent.Type.EnabledChange
            and not self.isEnabled()
        ):
            self._set_hover_circle_visible(False)

    def _set_hover_circle_visible(self, is_visible):
        if is_visible and self.isEnabled() and self.isVisible():
            circle = self._ensure_hover_circle()

            if circle is not None:
                self._position_hover_circle()
                circle.show()
                circle.stackUnder(self)
            return

        if self._hover_circle is not None:
            self._hover_circle.hide()

    def _ensure_hover_circle(self):
        parent = self.parentWidget()

        if parent is None:
            return None

        if (
            self._hover_circle is not None
            and self._hover_circle.parentWidget() is parent
        ):
            return self._hover_circle

        if self._hover_circle is not None:
            self._hover_circle.deleteLater()

        circle = QWidget(parent)
        circle.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        circle.setFixedSize(
            DETAIL_ICON_BUTTON_HOVER_SIZE,
            DETAIL_ICON_BUTTON_HOVER_SIZE,
        )
        circle.setStyleSheet(DETAIL_ICON_BUTTON_HOVER_STYLE)
        circle.hide()
        self.destroyed.connect(circle.deleteLater)
        self._hover_circle = circle
        return circle

    def _position_hover_circle(self):
        if self._hover_circle is None:
            return

        parent = self._hover_circle.parentWidget()

        if parent is None:
            return

        button_origin = self.mapTo(parent, QPoint(0, 0))
        offset = (
            DETAIL_ICON_BUTTON_HOVER_SIZE - DETAIL_ICON_BUTTON_SIZE
        ) // 2
        self._hover_circle.move(
            button_origin.x() - offset,
            button_origin.y() - offset,
        )


def make_icon_button(
    icon_name,
    parent=None,
    callback=None,
    *,
    tooltip=None,
    accessible_name=None,
):
    button = DetailIconButton(parent)
    button.setFixedSize(DETAIL_ICON_BUTTON_SIZE, DETAIL_ICON_BUTTON_SIZE)
    button.setIcon(QIcon(str(DETAIL_ICON_DIR / icon_name)))
    button.setIconSize(QSize(DETAIL_ICON_SIZE, DETAIL_ICON_SIZE))
    button.setStyleSheet(DETAIL_ICON_BUTTON_STYLE)
    button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    button.setCursor(Qt.CursorShape.PointingHandCursor)

    if tooltip:
        button.setToolTip(tooltip)

    button.setAccessibleName(accessible_name or tooltip or "")

    if callback is not None:
        button.clicked.connect(callback)

    return button


class DetailBlock(QFrame):
    def __init__(
        self,
        title,
        icon_name=None,
        parent=None,
        *,
        action_tooltip=None,
    ):
        super().__init__(parent)

        self.setObjectName("detailBlock")
        self.action_button = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 10, 12, 12)
        self.main_layout.setSpacing(5)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(DETAIL_HEADER_ICON_TEXT_SPACING)

        if icon_name:
            self.action_button = make_icon_button(
                icon_name,
                self,
                tooltip=action_tooltip,
            )
            header_layout.addWidget(self.action_button)

        title_label = QLabel(title, self)
        title_label.setObjectName("blockTitle")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(3)

        self.main_layout.addLayout(header_layout)
        self.main_layout.addLayout(self.body_layout, stretch=1)


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        widget = item.widget()

        if child_layout is not None:
            clear_layout(child_layout)

        if widget is not None:
            widget.deleteLater()
