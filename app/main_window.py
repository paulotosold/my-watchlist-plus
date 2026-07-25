from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from app.filtered_media import FilteredMedia
from app.find_media_handler import handle_find_media_input
from app.history_page import HistoryPage
from app.library_filter import DEFAULT_FILTER_TEXT
from app.media_details_dialog import open_media_details_dialog
from app.media_draft_builder import build_media_draft_from_db
from app.media_repository import get_media_by_id
from app.watchlist_page import WatchlistPage
from app.watchlist_status_control import WatchlistStatusBar
from db.connection import get_connection


TAB_STYLE = """
QTabBar::tab {
    background: #e8e8e8;
    border: 1px solid transparent;
    min-width: 120px;
    padding: 8px 18px;
}
QTabBar::tab:first {
    border-top-left-radius: 9px;
    border-bottom-left-radius: 9px;
}
QTabBar::tab:last {
    border-top-right-radius: 9px;
    border-bottom-right-radius: 9px;
}
QTabBar::tab:selected {
    background: white;
    border-color: #d0d0d0;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("My Watchlist+")
        self.setMinimumSize(900, 600)
        self.resize(1440, 900)

        central_widget = QWidget()
        central_widget.setObjectName("central-widget")
        central_widget.setStyleSheet(
            "#central-widget {background-color: #F1F1F1;}"
        )
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 14, 24, 0)
        main_layout.setSpacing(10)

        self.section_tabs = QTabBar(self)
        self.section_tabs.setObjectName("mainSectionTabs")
        self.section_tabs.setDrawBase(False)
        self.section_tabs.setExpanding(False)
        self.section_tabs.setStyleSheet(TAB_STYLE)

        tabs_layout = QHBoxLayout()
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.addStretch()
        tabs_layout.addWidget(self.section_tabs)
        tabs_layout.addStretch()
        main_layout.addLayout(tabs_layout)

        self.page_stack = QStackedWidget(self)
        main_layout.addWidget(self.page_stack, 1)

        self.status_bar = WatchlistStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.watchlist_status_control = (
            self.status_bar.watchlist_control
        )
        self.history_status_control = (
            self.status_bar.history_control
        )
        self.posters_per_row_control = (
            self.watchlist_status_control.poster_size_control
        )
        self._pages = []

        self.watchlist_page = WatchlistPage(self)
        self.history_page = HistoryPage(self)
        self._register_page("Watchlist", self.watchlist_page)
        self._register_page("History", self.history_page)

        # Compatibility aliases for callers that still inspect the old shell.
        self.top_bar = self.watchlist_page.top_bar
        self.media_board = self.watchlist_page.media_board

        self.section_tabs.currentChanged.connect(self._activate_page)
        self.posters_per_row_control.value_changed.connect(
            self._on_posters_per_row_changed
        )
        self.history_status_control.view_mode_requested.connect(
            self._set_history_view_mode
        )
        self.history_status_control.posters_per_row_requested.connect(
            self._set_history_posters_per_row
        )
        self.watchlist_status_control.reload_requested.connect(
            self._reload_watchlist
        )
        self.watchlist_status_control.pinned_only_requested.connect(
            self._set_watchlist_pinned_only
        )
        self.watchlist_status_control.clear_all_pins_requested.connect(
            self._clear_all_watchlist_pins
        )
        self.watchlist_page.watchlist_state_changed.connect(
            self._on_watchlist_state_changed
        )
        history_view_state_changed = getattr(
            self.history_page,
            "view_state_changed",
            None,
        )

        if history_view_state_changed is not None:
            history_view_state_changed.connect(
                self._on_history_view_state_changed
            )

        self.section_tabs.setCurrentIndex(0)
        self.page_stack.setCurrentIndex(0)
        self.watchlist_page.ensure_loaded()
        self._show_active_status()

    @property
    def filtered_media(self):
        return self.watchlist_page.filtered_media

    @filtered_media.setter
    def filtered_media(self, value):
        self.watchlist_page.filtered_media = value

    @property
    def active_page(self):
        index = self.page_stack.currentIndex()

        if 0 <= index < len(self._pages):
            return self._pages[index]

        return None

    def _register_page(self, label, page):
        index = self.section_tabs.addTab(label)
        self.page_stack.insertWidget(index, page)
        self._pages.insert(index, page)

        page.status_message_changed.connect(
            lambda message, source=page: self._on_page_status_message(
                source,
                message,
            )
        )
        page.find_media_requested.connect(
            lambda media_query, source_page=page: self.on_find_media_input(
                media_query,
                source_page=source_page,
            )
        )
        page.details_requested.connect(self.on_details_requested)
        page.library_changed.connect(
            lambda source=page: self._on_page_library_changed(source)
        )

    def _activate_page(self, index):
        if not 0 <= index < len(self._pages):
            return

        self.page_stack.setCurrentIndex(index)
        page = self._pages[index]
        page.ensure_loaded()
        self._show_active_status()

    def _on_posters_per_row_changed(self, posters_per_row):
        setter = getattr(
            self.watchlist_page,
            "set_posters_per_row",
            None,
        )

        if callable(setter):
            setter(posters_per_row)

    def _update_watchlist_status_visibility(self):
        is_watchlist = self.active_page is self.watchlist_page
        is_history = self.active_page is self.history_page
        active_control = (
            "watchlist"
            if is_watchlist
            else "history"
            if is_history
            else None
        )
        self.status_bar.set_active_control(active_control)
        self.posters_per_row_control.setVisible(is_watchlist)

    def _update_posters_per_row_control_visibility(self):
        self._update_watchlist_status_visibility()

    def _on_page_status_message(self, page, _message):
        if page is self.active_page and page is self.history_page:
            self._sync_history_status()

    def _on_watchlist_state_changed(
        self,
        filtered_count,
        pinned_count,
        pinned_only,
    ):
        self.watchlist_status_control.set_state(
            filtered_count,
            pinned_count,
            pinned_only,
        )

    def _sync_watchlist_status(self):
        self._on_watchlist_state_changed(
            self.watchlist_page.filtered_count,
            self.watchlist_page.pinned_count,
            self.watchlist_page.pinned_only,
        )

    def _set_history_view_mode(self, view_mode):
        setter = getattr(self.history_page, "set_view_mode", None)

        if callable(setter):
            setter(view_mode)

        self._sync_history_status()

    def _set_history_posters_per_row(self, posters_per_row):
        setter = getattr(
            self.history_page,
            "set_posters_per_row",
            None,
        )

        if callable(setter):
            setter(posters_per_row)

        self._sync_history_status()

    def _on_history_view_state_changed(
        self,
        view_mode,
        posters_per_row,
    ):
        self._sync_history_status(
            view_mode=view_mode,
            posters_per_row=posters_per_row,
        )

    def _sync_history_status(
        self,
        *,
        view_mode=None,
        posters_per_row=None,
    ):
        watched_count = _status_message_count(
            getattr(self.history_page, "status_message", "")
        )

        view_mode = view_mode or getattr(
            self.history_page,
            "view_mode",
            "list",
        )
        posters_per_row = (
            posters_per_row
            if posters_per_row is not None
            else getattr(
                self.history_page,
                "posters_per_row",
                18,
            )
        )
        self.history_status_control.set_state(
            watched_count,
            view_mode,
            posters_per_row,
        )

    def _reload_watchlist(self):
        reload_button = self.watchlist_status_control.reload_button
        reload_button.setEnabled(False)

        try:
            self.watchlist_page.reload_default_filter()
        finally:
            reload_button.setEnabled(True)
            self._sync_watchlist_status()

    def _set_watchlist_pinned_only(self, pinned_only):
        self.watchlist_page.set_pinned_only(pinned_only)

    def _clear_all_watchlist_pins(self):
        self.watchlist_page.clear_all_pins()

    def _on_page_library_changed(self, source_page):
        for page in self._pages:
            if page is not source_page:
                page.invalidate()

        self._show_active_status()

    def on_filter_input(self, filter_text):
        """Compatibility entry point for the former monolithic Watchlist."""
        if hasattr(self, "watchlist_page"):
            return self.watchlist_page.on_filter_input(filter_text)

        if filter_text != DEFAULT_FILTER_TEXT:
            print("Filter Library:", filter_text)
            return

        self.filtered_media = FilteredMedia()
        self.refresh_media_view()

    def on_find_media_input(self, media_query, *, source_page=None):
        print("Find Media:", media_query)
        result = handle_find_media_input(self, media_query)

        if result and result.get("status") in {"saved", "deleted"}:
            source_page = source_page or getattr(self, "active_page", None)
            top_bar = getattr(source_page, "top_bar", None)
            find_media_input = getattr(top_bar, "find_media_input", None)

            if find_media_input is not None:
                find_media_input.clear()

            self._refresh_after_media_change()

        return result

    def on_details_requested(self, details_request):
        try:
            media_draft = self._resolve_details_request(details_request)
        except Exception as exc:
            QMessageBox.warning(self, "Media Details", str(exc))
            return {"status": "cancelled"}

        if media_draft is None:
            QMessageBox.warning(
                self,
                "Media Details",
                "This media is no longer available in the library.",
            )
            return {"status": "cancelled"}

        result = open_media_details_dialog(self, media_draft)

        if result and result.get("status") in {"saved", "deleted"}:
            self._refresh_after_media_change()

        return result

    def _resolve_details_request(self, details_request):
        if isinstance(details_request, dict):
            return details_request

        media_id = int(details_request)

        with get_connection() as conn:
            media_row = get_media_by_id(conn, media_id)

            if media_row is None:
                return None

            return build_media_draft_from_db(conn, media_row)

    def refresh_media_view(self):
        """Refresh the active page now and defer other pages until activation."""
        active_page = self.active_page

        for page in self._pages:
            page.invalidate()

        if active_page is not None:
            active_page.ensure_loaded()

        self._show_active_status()

    def _refresh_after_media_change(self):
        """Synchronize edits without rebuilding the watchlist grid."""
        active_page = self.active_page
        self.watchlist_page.refresh_preserving_grid()

        for page in self._pages:
            if page is not self.watchlist_page:
                page.invalidate()

        if active_page is not None and active_page is not self.watchlist_page:
            active_page.ensure_loaded()

        self._show_active_status()

    def _show_active_status(self):
        page = self.active_page
        self._update_watchlist_status_visibility()

        if page is self.watchlist_page:
            self.status_bar.clearMessage()
            self._sync_watchlist_status()
            return

        self.status_bar.clearMessage()

        if page is self.history_page:
            self._sync_history_status()

    def _update_status_bar(self):
        self._show_active_status()


def _status_message_count(message):
    first_token = str(message).strip().split(maxsplit=1)

    if not first_token:
        return 0

    try:
        return max(0, int(first_token[0]))
    except ValueError:
        return 0
