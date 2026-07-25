import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QLineEdit, QSizeGrip, QWidget

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
                find_media_input = Mock()
                source_page = SimpleNamespace(
                    top_bar=SimpleNamespace(
                        find_media_input=find_media_input,
                    )
                )
                harness = SimpleNamespace(
                    _refresh_after_media_change=Mock(),
                )

                with patch(
                    "app.main_window.handle_find_media_input",
                    return_value={"status": status},
                ) as handler:
                    MainWindow.on_find_media_input(
                        harness,
                        "tt1234567",
                        source_page=source_page,
                    )

                handler.assert_called_once_with(harness, "tt1234567")

                if should_refresh:
                    find_media_input.clear.assert_called_once_with()
                    harness._refresh_after_media_change.assert_called_once_with()
                else:
                    find_media_input.clear.assert_not_called()
                    harness._refresh_after_media_change.assert_not_called()


class FakePage(QWidget):
    status_message_changed = Signal(str)
    find_media_requested = Signal(str)
    details_requested = Signal(object)
    library_changed = Signal()

    def __init__(self, status_message, parent=None):
        super().__init__(parent)
        self.status_message = status_message
        self.top_bar = SimpleNamespace(
            find_media_input=QLineEdit(self),
        )
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
    watchlist_state_changed = Signal(int, int, bool)

    def __init__(self, parent=None):
        super().__init__("22 filtered titles", parent)
        self.filtered_count = 22
        self.pinned_count = 0
        self.pinned_only = False
        self.posters_per_row_values = []
        self.pinned_only_values = []
        self.reload_count = 0
        self.preserved_refresh_count = 0
        self.clear_all_pins_count = 0

    def on_filter_input(self, filter_text):
        self.last_filter_text = filter_text

    def set_posters_per_row(self, value):
        self.posters_per_row_values.append(value)

    def reload_default_filter(self):
        self.reload_count += 1
        self.pinned_only = False
        self.watchlist_state_changed.emit(
            self.filtered_count,
            self.pinned_count,
            self.pinned_only,
        )

    def refresh_preserving_grid(self):
        self.preserved_refresh_count += 1
        self.is_invalidated = False

    def set_pinned_only(self, pinned_only):
        self.pinned_only_values.append(pinned_only)
        self.pinned_only = bool(pinned_only and self.pinned_count)
        self.watchlist_state_changed.emit(
            self.filtered_count,
            self.pinned_count,
            self.pinned_only,
        )

    def clear_all_pins(self):
        self.clear_all_pins_count += 1
        self.pinned_count = 0
        self.pinned_only = False
        self.watchlist_state_changed.emit(
            self.filtered_count,
            self.pinned_count,
            self.pinned_only,
        )


class FakeHistoryPage(FakePage):
    view_state_changed = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__("19 watched entries", parent)
        self.entries = [object() for _ in range(19)]
        self.view_mode = "list"
        self.posters_per_row = 18
        self.view_mode_values = []
        self.history_posters_per_row_values = []

    def set_view_mode(self, view_mode):
        if view_mode == self.view_mode:
            return False

        self.view_mode = view_mode
        self.view_mode_values.append(view_mode)
        self.view_state_changed.emit(
            self.view_mode,
            self.posters_per_row,
        )
        return True

    def set_posters_per_row(self, posters_per_row):
        if posters_per_row == self.posters_per_row:
            return False

        self.posters_per_row = posters_per_row
        self.history_posters_per_row_values.append(posters_per_row)
        self.view_state_changed.emit(
            self.view_mode,
            self.posters_per_row,
        )
        return True


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
            "",
        )
        self.assertFalse(self.window.watchlist_status_control.isHidden())
        self.assertTrue(self.window.history_status_control.isHidden())
        self.assertEqual(
            self.window.watchlist_status_control.filtered_label.text(),
            "22 filtered titles",
        )
        self.assertEqual(
            self.window.watchlist_status_control.pinned_button.text(),
            "0 pinned",
        )
        self.assertTrue(
            self.window.watchlist_status_control.pinned_pill.isHidden()
        )

        history_page = self.window.history_page
        self.window.section_tabs.setCurrentIndex(1)

        self.assertIs(self.window.history_page, history_page)
        self.assertIs(self.window.page_stack.currentWidget(), history_page)
        self.assertEqual(history_page.load_count, 1)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "",
        )
        self.assertTrue(self.window.watchlist_status_control.isHidden())
        self.assertFalse(self.window.history_status_control.isHidden())
        self.assertEqual(
            self.window.history_status_control.count_label.text(),
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
        self.assertEqual(control.posters_per_row, 6)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "",
        )

        control.plus_button.click()

        self.assertEqual(control.posters_per_row, 5)
        self.assertEqual(
            self.window.watchlist_page.posters_per_row_values,
            [5],
        )
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "",
        )

        self.window.section_tabs.setCurrentIndex(1)
        self.assertTrue(control.isHidden())

        self.window.section_tabs.setCurrentIndex(0)
        self.assertFalse(control.isHidden())
        self.assertEqual(control.posters_per_row, 5)

    def test_history_view_controls_are_forwarded_and_remembered(self):
        self.window.section_tabs.setCurrentIndex(1)
        control = self.window.history_status_control

        self.assertEqual(control.view_mode, "list")
        self.assertTrue(control.poster_size_control.isHidden())

        control.grid_view_button.click()

        self.assertEqual(
            self.window.history_page.view_mode_values,
            ["grid"],
        )
        self.assertEqual(control.view_mode, "grid")
        self.assertFalse(control.poster_size_control.isHidden())

        control.poster_size_control.minus_button.click()

        self.assertEqual(
            self.window.history_page.history_posters_per_row_values,
            [19],
        )
        self.assertEqual(control.posters_per_row, 19)

        self.window.section_tabs.setCurrentIndex(0)
        self.window.section_tabs.setCurrentIndex(1)

        self.assertEqual(control.view_mode, "grid")
        self.assertEqual(control.posters_per_row, 19)

    def test_status_messages_from_inactive_pages_are_ignored(self):
        self.window.history_page.status_message_changed.emit("new history")
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "",
        )

        self.window.watchlist_page.status_message = "21 filtered titles"
        self.window.watchlist_page.status_message_changed.emit(
            "21 filtered titles"
        )
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "",
        )

        self.window.section_tabs.setCurrentIndex(1)
        self.window.history_page.status_message_changed.emit("new history")
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "",
        )

    def test_watchlist_status_actions_are_forwarded_to_the_page(self):
        control = self.window.watchlist_status_control
        self.window.watchlist_page.pinned_count = 2
        self.window.watchlist_page.watchlist_state_changed.emit(
            22,
            2,
            False,
        )

        control.pinned_button.click()
        control.pinned_button.click()
        control.clear_pins_button.click()
        control.reload_button.click()

        self.assertEqual(
            self.window.watchlist_page.pinned_only_values,
            [True, False],
        )
        self.assertEqual(
            self.window.watchlist_page.clear_all_pins_count,
            1,
        )
        self.assertEqual(self.window.watchlist_page.reload_count, 1)

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
        self.window.watchlist_page.top_bar.find_media_input.setText(
            "keep this query"
        )
        self.window.history_page.top_bar.find_media_input.setText(
            "tt1234567"
        )

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
        self.assertEqual(
            self.window.watchlist_page.preserved_refresh_count,
            1,
        )
        self.assertFalse(self.window.watchlist_page.is_invalidated)
        self.assertEqual(
            self.window.watchlist_page.top_bar.find_media_input.text(),
            "keep this query",
        )
        self.assertEqual(
            self.window.history_page.top_bar.find_media_input.text(),
            "",
        )

    def test_cancelled_find_preserves_origin_input_and_does_not_refresh(self):
        find_media_input = self.window.watchlist_page.top_bar.find_media_input
        find_media_input.setText("unresolved query")

        with patch(
            "app.main_window.handle_find_media_input",
            return_value={"status": "cancelled"},
        ):
            self.window.watchlist_page.find_media_requested.emit(
                "unresolved query"
            )

        self.assertEqual(find_media_input.text(), "unresolved query")
        self.assertEqual(
            self.window.watchlist_page.preserved_refresh_count,
            0,
        )

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

    def test_saved_history_details_uses_stable_watchlist_refresh(self):
        media_draft = {"media_id": 42, "metadata": {"title": "Movie"}}
        self.window.section_tabs.setCurrentIndex(1)
        history_load_count = self.window.history_page.load_count

        with patch(
            "app.main_window.open_media_details_dialog",
            return_value={"status": "saved"},
        ) as open_details:
            self.window.history_page.details_requested.emit(media_draft)

        open_details.assert_called_once_with(self.window, media_draft)
        self.assertEqual(
            self.window.watchlist_page.preserved_refresh_count,
            1,
        )
        self.assertEqual(
            self.window.history_page.load_count,
            history_load_count + 1,
        )


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
        original_card_width = self.window.media_board.card_width

        self.window.posters_per_row_control.plus_button.click()
        self._process_events()

        self.assertEqual(self.window.media_board.posters_per_row, 5)
        self.assertGreater(
            self.window.media_board.card_width,
            original_card_width,
        )
        self.assertEqual(self.window.media_board.cards, original_cards)
        self.assertEqual(self.window.media_board.row_count, 2)
        self.assertEqual(
            self.window.status_bar.currentMessage(),
            "",
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
        self.assertEqual(self.window.posters_per_row_control.value(), 5)
        self.assertEqual(self.window.media_board.posters_per_row, 5)

    def test_status_scope_counts_and_clear_all_follow_the_real_board(self):
        board = self.window.media_board
        control = self.window.watchlist_status_control
        original_cards = list(board.cards)

        self.assertEqual(control.filtered_label.text(), "8 filtered titles")
        self.assertEqual(control.pinned_button.text(), "0 pinned")
        self.assertTrue(control.pinned_pill.isHidden())

        original_cards[1].on_pin_clicked()
        original_cards[5].on_pin_clicked()
        self._process_events()

        self.assertEqual(control.pinned_button.text(), "2 pinned")
        self.assertFalse(control.pinned_pill.isHidden())

        control.pinned_button.click()
        self._process_events()

        self.assertTrue(board.pinned_only)
        self.assertEqual(
            board.visible_cards,
            [original_cards[1], original_cards[5]],
        )
        self.assertEqual(control.filtered_label.text(), "8 filtered titles")
        self.assertTrue(control.pinned_button.isChecked())
        self.assertTrue(control.pinned_pill.property("active"))

        control.pinned_button.click()
        self._process_events()

        self.assertFalse(board.pinned_only)
        self.assertEqual(board.visible_cards, original_cards)
        self.assertFalse(control.pinned_button.isChecked())
        self.assertFalse(control.pinned_pill.property("active"))

        control.pinned_button.click()
        self._process_events()
        self.assertTrue(board.pinned_only)

        control.clear_pins_button.click()
        self._process_events()

        self.assertFalse(board.pinned_only)
        self.assertEqual(board.cards, original_cards)
        self.assertEqual(board.visible_cards, original_cards)
        self.assertEqual(control.pinned_button.text(), "0 pinned")
        self.assertTrue(control.pinned_pill.isHidden())

    def test_reload_restores_closed_cards_and_forces_filtered_scope(self):
        board = self.window.media_board
        control = self.window.watchlist_status_control
        pinned_card = board.cards[3]
        pinned_card.on_pin_clicked()
        board.cards[0].btn_close.click()
        self._process_events()
        pinned_index_before_reload = board.cards.index(pinned_card)

        control.pinned_button.click()
        self._process_events()
        self.assertTrue(board.pinned_only)
        self.assertEqual(control.filtered_label.text(), "7 filtered titles")

        control.reload_button.click()
        self._process_events()

        self.assertFalse(board.pinned_only)
        self.assertEqual(len(board.cards), 8)
        self.assertEqual(
            board.cards.index(pinned_card),
            pinned_index_before_reload,
        )
        self.assertTrue(pinned_card.is_pinned)
        self.assertEqual(control.filtered_label.text(), "8 filtered titles")
        self.assertEqual(control.pinned_button.text(), "1 pinned")
        self.assertFalse(control.pinned_pill.isHidden())
        self.assertFalse(control.pinned_pill.property("active"))

    def test_watchlist_viewport_meets_the_status_bar_without_a_gap(self):
        central_widget = self.window.centralWidget()
        viewport = self.window.watchlist_page.scroll_area.viewport()
        status_bar = self.window.status_bar

        self.assertEqual(
            central_widget.layout().contentsMargins().bottom(),
            0,
        )
        self.assertEqual(
            viewport.mapToGlobal(viewport.rect().bottomLeft()).y() + 1,
            status_bar.mapToGlobal(status_bar.rect().topLeft()).y(),
        )

    def test_pinned_pill_is_inset_within_the_status_bar(self):
        status_bar = self.window.status_bar
        control = self.window.watchlist_status_control
        self.window.media_board.cards[0].on_pin_clicked()
        self._process_events()
        pill = control.pinned_pill
        expected_margin = (
            status_bar.height() - pill.height()
        ) // 2

        self.assertEqual(control.geometry().top(), 0)
        self.assertEqual(control.height(), status_bar.height())
        self.assertGreater(control.width(), control.minimumSizeHint().width())
        self.assertEqual(
            pill.mapTo(
                status_bar,
                pill.rect().topLeft(),
            ).y(),
            expected_margin,
        )
        self.assertEqual(
            status_bar.rect().bottom()
            - pill.mapTo(
                status_bar,
                pill.rect().bottomLeft(),
            ).y(),
            expected_margin,
        )

    def test_status_content_does_not_collapse_before_grip_layout(self):
        status_bar = self.window.status_bar
        control = self.window.watchlist_status_control
        size_grip = status_bar.findChild(QSizeGrip)

        self.assertIsNotNone(size_grip)
        for transient_x in (0, 1):
            with self.subTest(transient_x=transient_x):
                size_grip.setGeometry(transient_x, 0, 17, 17)
                size_grip.show()

                status_bar._layout_watchlist_control()

                self.assertEqual(
                    control.width(),
                    status_bar.width() - size_grip.width(),
                )

    def test_history_status_uses_full_width_and_twelve_pixel_insets(self):
        self.window.section_tabs.setCurrentIndex(1)
        self._process_events()
        status_bar = self.window.status_bar
        control = self.window.history_status_control
        size_grip = status_bar.findChild(QSizeGrip)

        self.assertFalse(control.isHidden())
        self.assertTrue(self.window.watchlist_status_control.isHidden())
        self.assertEqual(control.geometry().top(), 0)
        self.assertEqual(control.height(), status_bar.height())
        self.assertEqual(
            control.width(),
            status_bar.width() - size_grip.width(),
        )
        self.assertEqual(
            control.count_label.mapTo(
                control,
                control.count_label.rect().topLeft(),
            ).x(),
            12,
        )
        self.assertEqual(
            control.width()
            - control.grid_view_button.geometry().right()
            - 1,
            12,
        )

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
