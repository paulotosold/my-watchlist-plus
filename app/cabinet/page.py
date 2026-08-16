"""Lazy-loaded Cabinet page."""

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QMessageBox, QScrollArea, QVBoxLayout, QWidget

from app.ui.top_bar import TopBar
from db.connection import get_connection

from .board import DEFAULT_POSTERS_PER_ROW, CabinetBoard
from .repository import initialize_and_load_cabinet, persist_cabinet_reorder


CABINET_BACKGROUND_COLOR = "#F1F1F1"


class CabinetPage(QWidget):
    status_message_changed = Signal(str)
    view_state_changed = Signal(int, int)
    find_media_requested = Signal(str)
    details_requested = Signal(object)

    def __init__(self, parent=None, *, posters_per_row=DEFAULT_POSTERS_PER_ROW):
        super().__init__(parent)
        self._is_loaded = False
        self._is_invalidated = True
        self._status_message = ""
        self._pending_scroll_anchor = None
        self._last_viewport_width = None

        self.top_bar = TopBar()
        self.media_board = CabinetBoard(posters_per_row=posters_per_row)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("cabinetScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.viewport().setObjectName("cabinetScrollViewport")
        self.media_board.setObjectName("cabinetScrollContent")
        self.scroll_area.setStyleSheet(
            f"""
            QScrollArea#cabinetScrollArea,
            QWidget#cabinetScrollViewport,
            QWidget#cabinetScrollContent {{
                background-color: {CABINET_BACKGROUND_COLOR};
            }}
            """
        )
        self.scroll_area.setWidget(self.media_board)
        self.media_board.set_scroll_area(self.scroll_area)
        self.scroll_area.viewport().installEventFilter(self)
        self.media_board.set_layout_width(max(1, self.scroll_area.viewport().width()))

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_viewport_resize)
        self._anchor_restore_timer = QTimer(self)
        self._anchor_restore_timer.setSingleShot(True)
        self._anchor_restore_timer.timeout.connect(self._restore_scroll_anchor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.top_bar)
        layout.addWidget(self.scroll_area, 1)

        self.top_bar.find_media_submitted.connect(self.find_media_requested.emit)
        self.media_board.details_requested.connect(self.details_requested.emit)
        self.media_board.view_state_changed.connect(self._on_view_state_changed)
        self.media_board.reorder_requested.connect(self._persist_reorder)

    @property
    def status_message(self):
        return self._status_message

    @property
    def is_loaded(self):
        return self._is_loaded

    @property
    def is_invalidated(self):
        return self._is_invalidated

    @property
    def posters_per_row(self):
        return self.media_board.posters_per_row

    @property
    def title_count(self):
        return len(self.media_board.cards)

    def ensure_loaded(self):
        if not self._is_loaded or self._is_invalidated:
            return self.refresh_media_view()
        return [card.current_media for card in self.media_board.cards]

    def invalidate(self):
        self._is_invalidated = True

    def clear_find_media_query(self):
        self.top_bar.find_media_input.clear()

    def set_posters_per_row(self, posters_per_row):
        anchor = self._capture_scroll_anchor()
        changed = self.media_board.set_posters_per_row(posters_per_row)
        if changed:
            self._pending_scroll_anchor = anchor
            self._anchor_restore_timer.start(0)
        return changed

    def refresh_media_view(self):
        with get_connection() as conn:
            media_drafts = initialize_and_load_cabinet(conn)
        self.media_board.load_media(media_drafts)
        self._is_loaded = True
        self._is_invalidated = False
        return media_drafts

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            if event.size().width() != self._last_viewport_width:
                self._pending_scroll_anchor = self._capture_scroll_anchor()
                self._last_viewport_width = event.size().width()
                self._resize_timer.start(0)
        return super().eventFilter(watched, event)

    def _apply_viewport_resize(self):
        self.media_board.set_layout_width(max(1, self.scroll_area.viewport().width()))
        self.media_board.reflow_cards()
        self._anchor_restore_timer.start(0)

    def _capture_scroll_anchor(self):
        if not self.media_board.cards:
            return None
        scroll_value = self.scroll_area.verticalScrollBar().value()
        for card in self.media_board.cards:
            if card.geometry().bottom() >= scroll_value:
                return card.get_current_media_key(), scroll_value - card.geometry().top()
        return None

    def _restore_scroll_anchor(self):
        anchor = self._pending_scroll_anchor
        self._pending_scroll_anchor = None
        if anchor is None:
            return
        media_id, offset = anchor
        for card in self.media_board.cards:
            if card.get_current_media_key() == media_id:
                self.scroll_area.verticalScrollBar().setValue(
                    card.geometry().top() + offset
                )
                return

    def _persist_reorder(self, expected_media_ids, desired_media_ids):
        try:
            with get_connection() as conn:
                result = persist_cabinet_reorder(
                    conn,
                    expected_media_ids,
                    desired_media_ids,
                )
        except Exception as exc:
            self.media_board.reject_reorder()
            QMessageBox.warning(self, "Reorder Cabinet", str(exc))
            return
        self.media_board.confirm_reorder(result)

    def _on_view_state_changed(self, title_count, posters_per_row):
        noun = "title" if title_count == 1 else "titles"
        self._status_message = (
            f"{title_count} {noun} -- Showing: Cabinet Worthy, Custom Order"
        )
        self.status_message_changed.emit(self._status_message)
        self.view_state_changed.emit(title_count, posters_per_row)
