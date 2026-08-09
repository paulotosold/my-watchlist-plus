import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.history.entry_widget import HistoryEntryWidget, POSTER_WIDTH
from app.history.page import HistoryPage
from app.history.repository import (
    HISTORY_DEFAULT_FILTER_TEXT,
    HistoryEntry,
)
from app.media_repository import ConcurrentEditError


class FakeConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        self.statements.append(statement)
        return self


def make_entry(
    key,
    *,
    state_media_id=10,
    details_media_id=None,
    title="Movie",
    media_type="movie",
    watch_state="watched",
    impression="good",
    is_collection_pick=False,
    poster=None,
):
    details_media_id = details_media_id or state_media_id
    return HistoryEntry(
        key=("media_event", key),
        kind="media_event",
        watch_history_ids=(key,),
        owner_media_ids=(state_media_id,),
        state_media_id=state_media_id,
        details_media_id=details_media_id,
        title=title,
        date_earliest="2026-07-10",
        date_latest="2026-07-10",
        created_at="2026-07-10 20:00:00",
        release_date="2020-01-01",
        formatted_date="10 Jul 2026, Fri",
        sort_key=(1, 3, (), key),
        poster=poster,
        media_type=media_type,
        watch_state=watch_state,
        impression=impression,
        is_collection_pick=is_collection_pick,
    )


class HistoryPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.entries = [
            make_entry(1, title="First"),
            make_entry(2, title="Rewatch"),
        ]
        self.connections = []

        def get_connection():
            connection = FakeConnection()
            self.connections.append(connection)
            return connection

        self.connection_patch = patch(
            "app.history.page.get_connection",
            side_effect=get_connection,
        )
        self.load_patch = patch(
            "app.history.page.load_default_history_entries",
            side_effect=lambda _conn: list(self.entries),
        )
        self.connection_patch.start()
        self.load_mock = self.load_patch.start()
        self.page = HistoryPage()

    def tearDown(self):
        self.page.close()
        self.load_patch.stop()
        self.connection_patch.stop()
        self.application.processEvents()

    def test_page_is_lazy_and_default_load_builds_vertical_history(self):
        self.assertFalse(self.page.is_loaded)
        self.assertTrue(self.page.is_invalidated)
        self.load_mock.assert_not_called()

        status_spy = QSignalSpy(self.page.status_message_changed)
        self.page.ensure_loaded()

        self.assertTrue(self.page.is_loaded)
        self.assertFalse(self.page.is_invalidated)
        self.assertEqual(len(self.page.entry_widgets), 2)
        self.assertEqual(self.page.status_message, "2 watched entries")
        self.assertEqual(status_spy.at(0), ["2 watched entries"])
        self.assertEqual(
            self.page.scroll_area.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            self.page.top_bar.filter_input.text(),
            HISTORY_DEFAULT_FILTER_TEXT,
        )

    def test_switch_style_ensure_loaded_preserves_loaded_page_until_invalidated(self):
        self.page.ensure_loaded()
        first_widgets = list(self.page.entry_widgets)

        self.page.ensure_loaded()

        self.assertEqual(self.load_mock.call_count, 1)
        self.assertEqual(self.page.entry_widgets, first_widgets)

        self.page.invalidate()
        self.assertEqual(self.load_mock.call_count, 1)

        self.page.ensure_loaded()
        self.assertEqual(self.load_mock.call_count, 2)

    def test_clear_find_media_query_clears_only_its_input(self):
        self.page.top_bar.filter_input.setText("keep filter")
        self.page.top_bar.find_media_input.setText("tt1234567")

        self.page.clear_find_media_query()

        self.assertEqual(self.page.top_bar.find_media_input.text(), "")
        self.assertEqual(self.page.top_bar.filter_input.text(), "keep filter")

    def test_default_filter_reloads_and_resets_scroll_but_other_text_only_prints(self):
        self.entries = [
            make_entry(index, title=f"Movie {index}")
            for index in range(1, 9)
        ]
        self.page.resize(1000, 420)
        self.page.show()
        self.page.ensure_loaded()
        self.page.scroll_content.setMinimumHeight(3000)
        self.application.processEvents()
        self.application.processEvents()

        scroll_bar = self.page.scroll_area.verticalScrollBar()
        self.assertGreater(scroll_bar.maximum(), 0)
        scroll_bar.setValue(scroll_bar.maximum())

        self.page.on_filter_input(HISTORY_DEFAULT_FILTER_TEXT)
        self.application.processEvents()

        self.assertEqual(self.load_mock.call_count, 2)
        self.assertEqual(scroll_bar.value(), 0)

        with patch("builtins.print") as print_mock:
            self.page.on_filter_input("only comedies")

        print_mock.assert_called_once_with("Filter History:", "only comedies")
        self.assertEqual(self.load_mock.call_count, 2)

    def test_invalidated_reload_restores_scroll_after_range_rebuild(self):
        self.entries = [
            make_entry(index, title=f"Movie {index}")
            for index in range(1, 9)
        ]
        self.page.resize(1000, 420)
        self.page.show()
        self.page.ensure_loaded()

        for _ in range(3):
            self.application.processEvents()

        scroll_bar = self.page.scroll_area.verticalScrollBar()
        target = min(700, scroll_bar.maximum())
        self.assertGreater(target, 0)
        scroll_bar.setValue(target)

        self.entries.extend(
            make_entry(index, title=f"Movie {index}")
            for index in range(9, 13)
        )
        self.page.invalidate()
        self.page.ensure_loaded()

        for _ in range(4):
            self.application.processEvents()

        self.assertEqual(scroll_bar.value(), target)

    def test_title_requests_parent_details_media(self):
        self.entries = [
            make_entry(
                1,
                state_media_id=30,
                details_media_id=99,
                title="Fallout (S1:E1-3)",
            )
        ]
        self.page.ensure_loaded()
        details_spy = QSignalSpy(self.page.details_requested)

        self.page.entry_widgets[0].title_label.activated.emit()

        self.assertEqual(details_spy.at(0), [99])

    def test_population_and_repeated_value_do_not_save(self):
        self.page.ensure_loaded()

        with patch(
            "app.history.page.apply_media_state_patch"
        ) as apply_patch_mock:
            combo = self.page.entry_widgets[0].impression_combo
            combo.activated.emit(combo.currentIndex())

        apply_patch_mock.assert_not_called()

    def test_successful_activation_saves_once_and_syncs_duplicate_rows(self):
        self.page.ensure_loaded()
        library_spy = QSignalSpy(self.page.library_changed)
        first_widget, second_widget = self.page.entry_widgets

        def persist(_conn, media_id, expected_values, changes):
            self.assertEqual(media_id, 10)
            self.assertFalse(first_widget.impression_combo.isEnabled())
            self.assertFalse(second_widget.collection_combo.isEnabled())
            self.assertEqual(expected_values, {"impression": "good"})
            self.assertEqual(changes, {"impression": "very_good"})
            return {
                "media_id": media_id,
                "watch_state": "watched",
                "impression": "very_good",
                "is_collection_pick": False,
            }

        with patch(
            "app.history.page.apply_media_state_patch",
            side_effect=persist,
        ) as apply_patch_mock:
            combo = first_widget.impression_combo
            combo.setCurrentIndex(combo.findData("very_good"))
            combo.activated.emit(combo.currentIndex())

        apply_patch_mock.assert_called_once()
        self.assertEqual(first_widget.impression_combo.currentData(), "very_good")
        self.assertEqual(second_widget.impression_combo.currentData(), "very_good")
        self.assertTrue(all(
            entry.impression == "very_good"
            for entry in self.page.entries
        ))
        self.assertTrue(first_widget.impression_combo.isEnabled())
        self.assertTrue(second_widget.collection_combo.isEnabled())
        self.assertEqual(library_spy.count(), 1)
        self.assertIn("BEGIN IMMEDIATE", self.connections[-1].statements)

    def test_status_activation_saves_once_and_syncs_duplicate_rows(self):
        self.page.ensure_loaded()
        library_spy = QSignalSpy(self.page.library_changed)
        first_widget, second_widget = self.page.entry_widgets

        def persist(_conn, media_id, expected_values, changes):
            self.assertEqual(media_id, 10)
            self.assertFalse(first_widget.status_combo.isEnabled())
            self.assertFalse(second_widget.impression_combo.isEnabled())
            self.assertEqual(expected_values, {"watch_state": "watched"})
            self.assertEqual(changes, {"watch_state": "to_watch"})
            return {
                "media_id": media_id,
                "watch_state": "to_watch",
                "impression": "good",
                "is_collection_pick": False,
            }

        with patch(
            "app.history.page.apply_media_state_patch",
            side_effect=persist,
        ) as apply_patch_mock:
            combo = first_widget.status_combo
            combo.setCurrentIndex(combo.findData("to_watch"))
            combo.activated.emit(combo.currentIndex())

        apply_patch_mock.assert_called_once()
        self.assertEqual(first_widget.status_combo.currentData(), "to_watch")
        self.assertEqual(second_widget.status_combo.currentData(), "to_watch")
        self.assertTrue(all(
            entry.watch_state == "to_watch"
            for entry in self.page.entries
        ))
        self.assertTrue(first_widget.status_combo.isEnabled())
        self.assertTrue(second_widget.collection_combo.isEnabled())
        self.assertEqual(library_spy.count(), 1)

    def test_failed_save_rolls_back_to_confirmed_values(self):
        self.page.ensure_loaded()
        first_widget, second_widget = self.page.entry_widgets

        with (
            patch(
                "app.history.page.apply_media_state_patch",
                side_effect=RuntimeError("database is busy"),
            ),
            patch("app.history.page.QMessageBox.warning") as warning,
        ):
            combo = first_widget.collection_combo
            combo.setCurrentIndex(combo.findData(True))
            combo.activated.emit(combo.currentIndex())

        self.assertFalse(first_widget.collection_combo.currentData())
        self.assertFalse(second_widget.collection_combo.currentData())
        warning.assert_called_once()
        self.assertIn("database is busy", warning.call_args.args[2])

    def test_conflict_loads_canonical_state_and_warns(self):
        self.page.ensure_loaded()
        first_widget, second_widget = self.page.entry_widgets
        library_spy = QSignalSpy(self.page.library_changed)

        with (
            patch(
                "app.history.page.apply_media_state_patch",
                side_effect=ConcurrentEditError("changed"),
            ),
            patch(
                "app.history.page.get_media_state",
                return_value={
                    "media_id": 10,
                    "watch_state": "watched",
                    "impression": "meh",
                    "is_collection_pick": True,
                },
            ) as reload_state,
            patch("app.history.page.QMessageBox.warning") as warning,
        ):
            combo = first_widget.impression_combo
            combo.setCurrentIndex(combo.findData("very_good"))
            combo.activated.emit(combo.currentIndex())

        reload_state.assert_called_once()
        self.assertEqual(first_widget.impression_combo.currentData(), "meh")
        self.assertEqual(second_widget.impression_combo.currentData(), "meh")
        self.assertTrue(first_widget.collection_combo.currentData())
        self.assertTrue(second_widget.collection_combo.currentData())
        self.assertTrue(all(
            entry.impression == "meh"
            and entry.is_collection_pick is True
            for entry in self.page.entries
        ))
        self.assertEqual(library_spy.count(), 1)
        warning.assert_called_once()
        self.assertIn("latest saved values", warning.call_args.args[2])

    def test_status_uses_singular_for_one_visible_row(self):
        self.entries = [make_entry(1)]
        self.page.ensure_loaded()

        self.assertEqual(self.page.status_message, "1 watched entry")


class HistoryEntryWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_poster_has_constant_width_and_preserves_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            poster_path = Path(directory) / "portrait.png"
            image = QImage(300, 600, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGray)
            self.assertTrue(image.save(str(poster_path)))

            entry = make_entry(
                1,
                poster={
                    "filename": "portrait.png",
                    "source": "user",
                    "curation_status": "selected",
                    "is_default": True,
                },
            )

            with patch(
                "app.history.entry_widget.POSTER_DIR",
                Path(directory),
            ):
                widget = HistoryEntryWidget(entry)

            try:
                self.assertEqual(widget.poster_label.width(), POSTER_WIDTH)
                self.assertEqual(widget.poster_label.height(), POSTER_WIDTH * 2)
            finally:
                widget.close()

    def test_state_fields_match_media_details_layout_and_options(self):
        widget = HistoryEntryWidget(make_entry(
            1,
            media_type="series",
            title="Black Mirror (S7:E6) – USS Callister: Into Infinity",
        ))

        try:
            widget.resize(1100, 320)
            widget.show()
            self.application.processEvents()
            field_layout = widget.details_widget.layout()
            expected_widgets = (
                widget.title_label,
                widget.status_label,
                widget.status_combo,
                widget.impression_label,
                widget.impression_combo,
                widget.collection_label,
                widget.collection_combo,
            )

            self.assertGreater(widget.details_widget.width(), 190)
            self.assertGreaterEqual(
                widget.title_label.contentsRect().width(),
                widget.title_label.fontMetrics().horizontalAdvance(
                    widget.title_label.text()
                ),
            )
            self.assertEqual(field_layout.spacing(), 4)
            self.assertEqual(
                tuple(
                    field_layout.itemAt(index).widget()
                    for index in range(len(expected_widgets))
                ),
                expected_widgets,
            )
            self.assertEqual(widget.status_label.text(), "Status")
            self.assertEqual(widget.impression_label.text(), "Impression")
            self.assertEqual(widget.collection_label.text(), "Collection Pick")

            for combo in (
                widget.status_combo,
                widget.impression_combo,
                widget.collection_combo,
            ):
                self.assertEqual(combo.width(), 190)
                self.assertGreaterEqual(combo.minimumHeight(), 30)

            self.assertEqual(widget.status_combo.currentData(), "watched")
            self.assertGreaterEqual(widget.status_combo.findData("dropped"), 0)
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
