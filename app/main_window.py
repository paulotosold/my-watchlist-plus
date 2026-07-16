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
        self.setFixedSize(1440, 900)

        central_widget = QWidget()
        central_widget.setObjectName("central-widget")
        central_widget.setStyleSheet(
            "#central-widget {background-color: #F1F1F1;}"
        )
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 14, 24, 18)
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

        self.status_bar = self.statusBar()
        self._pages = []

        self.watchlist_page = WatchlistPage(self)
        self.history_page = HistoryPage(self)
        self._register_page("Watchlist", self.watchlist_page)
        self._register_page("History", self.history_page)

        # Compatibility aliases for callers that still inspect the old shell.
        self.top_bar = self.watchlist_page.top_bar
        self.media_board = self.watchlist_page.media_board

        self.section_tabs.currentChanged.connect(self._activate_page)
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
        page.find_media_requested.connect(self.on_find_media_input)
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

    def _on_page_status_message(self, page, message):
        if page is self.active_page:
            self.status_bar.showMessage(message)

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

    def on_find_media_input(self, media_query):
        print("Find Media:", media_query)
        result = handle_find_media_input(self, media_query)

        if result and result.get("status") in {"saved", "deleted"}:
            self.refresh_media_view()

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
            self.refresh_media_view()

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

    def _show_active_status(self):
        page = self.active_page
        self.status_bar.showMessage(page.status_message if page else "")

    def _update_status_bar(self):
        self._show_active_status()
