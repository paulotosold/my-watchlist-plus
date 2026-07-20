import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget

from app.library_filter import DEFAULT_FILTER_TEXT
from app.main_window import MainWindow


class MainWindowInputTests(unittest.TestCase):
    def test_exact_default_filter_replaces_and_refreshes_filtered_media(self):
        replacement = object()
        harness = SimpleNamespace(
            filtered_media=object(),
            refresh_media_view=Mock(),
        )

        with patch(
            "app.main_window.FilteredMedia",
            return_value=replacement,
        ) as filtered_media_factory, patch("builtins.print") as print_mock:
            MainWindow.on_filter_input(harness, DEFAULT_FILTER_TEXT)

        filtered_media_factory.assert_called_once_with()
        print_mock.assert_not_called()
        self.assertIs(harness.filtered_media, replacement)
        harness.refresh_media_view.assert_called_once_with()

    def test_any_other_filter_text_is_only_printed(self):
        for filter_text in (
            "",
            DEFAULT_FILTER_TEXT.lower(),
            f" {DEFAULT_FILTER_TEXT}",
            f"{DEFAULT_FILTER_TEXT} ",
            "movies directed by Jane Campion",
        ):
            with self.subTest(filter_text=filter_text):
                current_filtered_media = object()
                harness = SimpleNamespace(
                    filtered_media=current_filtered_media,
                    refresh_media_view=Mock(),
                )

                with (
                    patch("app.main_window.FilteredMedia") as factory,
                    patch("builtins.print") as print_mock,
                ):
                    MainWindow.on_filter_input(harness, filter_text)

                print_mock.assert_called_once_with(
                    "Filter Library:",
                    filter_text,
                )
                factory.assert_not_called()
                self.assertIs(harness.filtered_media, current_filtered_media)
                harness.refresh_media_view.assert_not_called()

    def test_find_media_refreshes_only_after_saved_or_deleted(self):
        for status, should_refresh in (
            ("saved", True),
            ("deleted", True),
            ("cancelled", False),
        ):
            with self.subTest(status=status):
                harness = SimpleNamespace(refresh_media_view=Mock())

                with patch(
                    "app.main_window.handle_find_media_input",
                    return_value={"status": status},
                ) as handler:
                    MainWindow.on_find_media_input(harness, "tt1234567")

                handler.assert_called_once_with(harness, "tt1234567")

                if should_refresh:
                    harness.refresh_media_view.assert_called_once_with()
                else:
                    harness.refresh_media_view.assert_not_called()


class FakePage(QWidget):
    status_message_changed = Signal(str)
    find_media_requested = Signal(str)
    details_requested = Signal(object)
    library_changed = Signal()

    def __init__(self, status_message, parent=None):
        super().__init__(parent)
        self.status_message = status_message
        self.top_bar = object()
        self.media_board = object()
        self.filtered_media = object()
        self.is_invalidated = True
        self.load_count = 0
        self.ensure_count = 0
        self.invalidate_count = 0

    def ensure_loaded(self):
        self.ensure_count += 1

        if self.is_invalidated:
            self.load_count += 1
            self.is_invalidated = False

    def invalidate(self):
        self.invalidate_count += 1
        self.is_invalidated = True


class FakeWatchlistPage(FakePage):
    def __init__(self, parent=None):
        super().__init__("22 filtered media", parent)
        self.posters_per_row_values = []

    def on_filter_input(self, filter_text):
        self.last_filter_text = filter_text

    def set_posters_per_row(self, value):
        self.posters_per_row_values.append(value)


class FakeHistoryPage(FakePage):
    def __init__(self, parent=None):
        super().__init__("19 watched entries", parent)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeWatchlistFilteredMedia:
    def __init__(self, count=8):
        self.media_list = [
            {
                "media_id": index,
                "metadata": {"title": f"Media {index}"},
                "posters": [],
            }
            for index in range(count)
        ]

    def refresh(self):
        return self.media_list


class MainWindowShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.watchlist_patch = patch(
            "app.main_window.WatchlistPage",
            FakeWatchlistPage,
        )
        self.history_patch = patch(
            "app.main_window.HistoryPage",
            FakeHistoryPage,
        )
        self.watchlist_patch.start()
        self.history_patch.start()
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.history_patch.stop()
        self.watchlist_patch.stop()
        self.application.processEvents()

    def test_watchlist_is_default_and_history_is_loaded_lazily(self):
        self.assertEqual(self.window.section_tabs.currentIndex(), 0)
        self.assertIs(
            self.window.page_stack.currentWidget(),
            self.window.watchlist_page,
        )
        self.assertEqual(self.window.watchlist_page.load_count, 1)
        self.assertEqual(self.window.history_page.load_count, 0)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "22 filtered media",
        )

        history_page = self.window.history_page
        self.window.section_tabs.setCurrentIndex(1)

        self.assertIs(self.window.history_page, history_page)
        self.assertIs(self.window.page_stack.currentWidget(), history_page)
        self.assertEqual(history_page.load_count, 1)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "19 watched entries",
        )

        self.window.section_tabs.setCurrentIndex(0)
        self.window.section_tabs.setCurrentIndex(1)
        self.assertEqual(history_page.load_count, 1)

    def test_window_starts_large_and_can_resize_down_to_its_minimum(self):
        self.assertEqual(self.window.size().toTuple(), (1440, 900))
        self.assertEqual(self.window.minimumSize().toTuple(), (900, 600))

        self.window.resize(1000, 650)
        self.application.processEvents()
        self.assertEqual(self.window.size().toTuple(), (1000, 650))

        self.window.resize(700, 400)
        self.application.processEvents()
        self.assertEqual(self.window.size().toTuple(), (900, 600))

    def test_posters_control_is_watchlist_only_and_preserves_status(self):
        control = self.window.posters_per_row_control

        self.assertFalse(control.isHidden())
        self.assertEqual(control.posters_per_row, 5)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "22 filtered media",
        )

        control.increase_button.click()

        self.assertEqual(control.posters_per_row, 6)
        self.assertEqual(
            self.window.watchlist_page.posters_per_row_values,
            [6],
        )
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "22 filtered media",
        )

        self.window.section_tabs.setCurrentIndex(1)
        self.assertTrue(control.isHidden())

        self.window.section_tabs.setCurrentIndex(0)
        self.assertFalse(control.isHidden())
        self.assertEqual(control.posters_per_row, 6)

    def test_status_messages_from_inactive_pages_are_ignored(self):
        self.window.history_page.status_message_changed.emit("new history")
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "22 filtered media",
        )

        self.window.watchlist_page.status_message = "21 filtered media"
        self.window.watchlist_page.status_message_changed.emit(
            "21 filtered media"
        )
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "21 filtered media",
        )

    def test_inline_history_change_only_invalidates_other_pages(self):
        self.window.section_tabs.setCurrentIndex(1)
        history_load_count = self.window.history_page.load_count

        self.window.history_page.library_changed.emit()

        self.assertTrue(self.window.watchlist_page.is_invalidated)
        self.assertFalse(self.window.history_page.is_invalidated)
        self.assertEqual(
            self.window.history_page.load_count,
            history_load_count,
        )

    def test_saved_find_refreshes_active_and_defers_inactive_page(self):
        self.window.section_tabs.setCurrentIndex(1)
        history_load_count = self.window.history_page.load_count

        with patch(
            "app.main_window.handle_find_media_input",
            return_value={"status": "saved"},
        ) as handler:
            self.window.history_page.find_media_requested.emit("tt1234567")

        handler.assert_called_once_with(self.window, "tt1234567")
        self.assertEqual(
            self.window.history_page.load_count,
            history_load_count + 1,
        )
        self.assertTrue(self.window.watchlist_page.is_invalidated)

    def test_history_details_loads_one_full_draft_on_click(self):
        media_row = {"id": 42}
        media_draft = {"media_id": 42, "metadata": {"title": "Movie"}}

        with (
            patch(
                "app.main_window.get_connection",
                return_value=FakeConnection(),
            ),
            patch(
                "app.main_window.get_media_by_id",
                return_value=media_row,
            ) as get_media,
            patch(
                "app.main_window.build_media_draft_from_db",
                return_value=media_draft,
            ) as build_draft,
            patch(
                "app.main_window.open_media_details_dialog",
                return_value={"status": "cancelled"},
            ) as open_details,
        ):
            self.window.history_page.details_requested.emit(42)

        get_media.assert_called_once()
        build_draft.assert_called_once()
        open_details.assert_called_once_with(self.window, media_draft)


class MainWindowWatchlistIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.filtered_media = FakeWatchlistFilteredMedia()
        self.filtered_media_patch = patch(
            "app.watchlist_page.FilteredMedia",
            return_value=self.filtered_media,
        )
        self.history_connection_patch = patch(
            "app.history_page.get_connection",
            return_value=FakeConnection(),
        )
        self.history_entries_patch = patch(
            "app.history_page.load_default_history_entries",
            return_value=[],
        )
        self.filtered_media_patch.start()
        self.history_connection_patch.start()
        self.history_entries_patch.start()
        self.window = MainWindow()
        self.window.show()
        self._process_events()

    def tearDown(self):
        self.window.close()
        self.history_entries_patch.stop()
        self.history_connection_patch.stop()
        self.filtered_media_patch.stop()
        self.application.processEvents()

    def _process_events(self):
        for _ in range(6):
            self.application.processEvents()

    def test_status_control_reflows_the_real_board_and_survives_tabs(self):
        original_cards = list(self.window.media_board.cards)

        self.window.posters_per_row_control.increase_button.click()
        self._process_events()

        self.assertEqual(self.window.media_board.posters_per_row, 6)
        self.assertEqual(self.window.media_board.cards, original_cards)
        self.assertEqual(self.window.media_board.row_count, 2)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "8 filtered media",
        )

        self.window.section_tabs.setCurrentIndex(1)
        self.window.resize(1000, 650)
        self._process_events()

        self.assertTrue(self.window.posters_per_row_control.isHidden())
        self.assertEqual(self.window.size().toTuple(), (1000, 650))
        self.assertEqual(
            self.window.history_page.scroll_area
            .horizontalScrollBar().maximum(),
            0,
        )

        self.window.section_tabs.setCurrentIndex(0)
        self._process_events()

        self.assertFalse(self.window.posters_per_row_control.isHidden())
        self.assertEqual(self.window.posters_per_row_control.value(), 6)
        self.assertEqual(self.window.media_board.posters_per_row, 6)

    def test_window_supports_maximize_and_restore(self):
        self.assertGreater(self.window.maximumWidth(), 1440)
        self.assertGreater(self.window.maximumHeight(), 900)

        self.window.showMaximized()
        self._process_events()
        self.assertTrue(self.window.isMaximized())

        self.window.showNormal()
        self._process_events()
        self.assertFalse(self.window.isMaximized())
        self.assertEqual(self.window.size().toTuple(), (1440, 900))


if __name__ == "__main__":
    unittest.main()
