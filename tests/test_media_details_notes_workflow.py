import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QObject, QPoint, Signal, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QToolButton

from app.media_details.dialog import (
    ENTRY_ACTION_LINE_HEIGHT,
    MediaDetailsDialog,
)
from app.media_details.note_dialog import NotePreviewLabel
from app.media_state_controls import ClickableEntryLabel


class FakeRefreshManager(QObject):
    progress = Signal(str, object)
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    cancelled = Signal(str, object)
    finished = Signal(str, object)

    def start_refresh(self, media_id, match):
        return "refresh-job"

    def cancel(self, job_id):
        return True


class MediaDetailsNotesWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.load_lists_patch = patch.object(
            MediaDetailsDialog,
            "_load_all_lists",
            lambda dialog: setattr(
                dialog,
                "all_lists",
                [{"id": 1, "name": "Favorites", "description": None}],
            ),
        )
        self.load_lists_patch.start()

    def tearDown(self):
        self.load_lists_patch.stop()
        self.application.processEvents()

    def test_add_buttons_are_the_first_items_in_each_list_panel(self):
        dialog = self._dialog()

        for panel_layout in (
            dialog.watch_history_layout,
            dialog.notes_layout,
            dialog.lists_layout,
        ):
            with self.subTest(layout=panel_layout):
                self.assertIsInstance(panel_layout.itemAt(0).widget(), QToolButton)

        self.assertIsInstance(
            dialog.watch_history_layout.itemAt(1).widget(),
            ClickableEntryLabel,
        )

    def test_watch_history_and_note_texts_open_the_correct_details_dialogs(self):
        with (
            patch(
                "app.media_details.dialog.WatchEntryDetailsDialog",
            ) as watch_dialog,
            patch(
                "app.media_details.dialog.NoteDetailsDialog",
            ) as note_dialog,
        ):
            watch_dialog.return_value.exec.return_value = QDialog.Rejected
            note_dialog.return_value.exec.return_value = QDialog.Rejected
            dialog = self._dialog(notes=[{"id": 20, "note": "Clickable note"}])
            dialog.show()
            self.application.processEvents()

            watch_label = dialog.watch_history_layout.itemAt(1).widget()
            note_label = self._note_label(dialog, 1)
            QTest.mouseClick(
                watch_label,
                Qt.MouseButton.LeftButton,
                pos=QPoint(2, watch_label.height() // 2),
            )
            QTest.mouseClick(
                note_label,
                Qt.MouseButton.LeftButton,
                pos=QPoint(2, note_label.height() // 2),
            )

        watch_entry = watch_dialog.call_args.args[2]
        note_entry = note_dialog.call_args.args[1]
        self.assertEqual(watch_entry["watch_history_id"], 10)
        self.assertEqual(note_entry["id"], 20)
        self.assertEqual(note_entry["note_index"], 0)

    def test_notes_render_newest_first_as_literal_single_line_previews(self):
        newest_text = "<b>Newest</b>\nwith a second line and enough text to elide"
        dialog = self._dialog(notes=[
            {
                "id": 1,
                "note": "Oldest",
                "created_at": "2026-01-01 10:00:00",
            },
            {
                "id": 2,
                "note": newest_text,
                "created_at": "2026-01-02 10:00:00",
            },
        ])
        dialog.show()
        self.application.processEvents()

        newest_label = self._note_label(dialog, 1)
        oldest_label = self._note_label(dialog, 2)
        self.assertEqual(newest_label.full_text, newest_text)
        self.assertEqual(newest_label.preview_text, "<b>Newest</b> with a second line and enough text to elide")
        self.assertEqual(newest_label.toolTip(), newest_text)
        self.assertEqual(newest_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertNotIn("\n", newest_label.text())
        self.assertEqual(oldest_label.full_text, "Oldest")
        self.assertEqual(newest_label.height(), ENTRY_ACTION_LINE_HEIGHT)
        self.assertEqual(
            newest_label.height(),
            dialog.watch_history_layout.itemAt(1).widget().height(),
        )

        newest_label.resize(70, newest_label.height())
        self.application.processEvents()
        self.assertTrue(newest_label.text().endswith("…"))

    def test_add_note_updates_draft_marks_dirty_and_keeps_new_note_on_top(self):
        dialog = self._dialog(notes=[{"id": 1, "note": "Older"}])

        with patch(
            "app.media_details.dialog.NoteDetailsDialog",
        ) as note_dialog:
            note_dialog.return_value.exec.return_value = QDialog.Accepted
            note_dialog.return_value.result_payload = {
                "action": "save",
                "note": "Newer",
            }
            dialog.add_note()

        notes = dialog.media_draft["user_data"]["notes"]
        self.assertEqual([note["note"] for note in notes], ["Older", "Newer"])
        self.assertTrue(notes[1]["draft_id"])
        self.assertTrue(dialog._is_dirty)
        self.assertEqual(self._note_label(dialog, 1).full_text, "Newer")
        self.assertEqual(self._note_label(dialog, 2).full_text, "Older")

    def test_edit_preserves_order_and_delete_removes_the_selected_note(self):
        dialog = self._dialog(notes=[
            {"id": 1, "note": "Older", "created_at": "2026-01-01"},
            {"id": 2, "note": "Newer", "created_at": "2026-01-02"},
        ])
        older_entry = {
            **dialog.media_draft["user_data"]["notes"][0],
            "note_index": 0,
        }

        with patch(
            "app.media_details.dialog.NoteDetailsDialog",
        ) as note_dialog:
            note_dialog.return_value.exec.return_value = QDialog.Accepted
            note_dialog.return_value.result_payload = {
                "action": "save",
                "note": "Older edited",
            }
            dialog.edit_note(older_entry)

        self.assertEqual(
            [note["note"] for note in dialog.media_draft["user_data"]["notes"]],
            ["Older edited", "Newer"],
        )
        self.assertEqual(self._note_label(dialog, 1).full_text, "Newer")
        self.assertEqual(self._note_label(dialog, 2).full_text, "Older edited")

        newer_entry = {
            **dialog.media_draft["user_data"]["notes"][1],
            "note_index": 1,
        }

        with patch(
            "app.media_details.dialog.NoteDetailsDialog",
        ) as note_dialog:
            note_dialog.return_value.exec.return_value = QDialog.Accepted
            note_dialog.return_value.result_payload = {"action": "delete"}
            dialog.edit_note(newer_entry)

        self.assertEqual(
            dialog.media_draft["user_data"]["notes"],
            [{"id": 1, "note": "Older edited", "created_at": "2026-01-01"}],
        )

    def test_cancelled_note_dialog_leaves_draft_and_dirty_state_unchanged(self):
        dialog = self._dialog(notes=[{"id": 1, "note": "Original"}])

        with patch(
            "app.media_details.dialog.NoteDetailsDialog",
        ) as note_dialog:
            note_dialog.return_value.exec.return_value = QDialog.Rejected
            dialog.add_note()

        self.assertEqual(
            dialog.media_draft["user_data"]["notes"],
            [{"id": 1, "note": "Original"}],
        )
        self.assertFalse(dialog._is_dirty)

    def _note_label(self, dialog, layout_index):
        label = dialog.notes_layout.itemAt(layout_index).widget()
        self.assertIsInstance(label, NotePreviewLabel)
        return label

    def _dialog(self, notes=None):
        return MediaDetailsDialog(
            None,
            self._draft(notes or []),
            metadata_refresh_manager=FakeRefreshManager(),
        )

    def _draft(self, notes):
        return {
            "media_id": 1,
            "metadata": {
                "tmdb_id": 100,
                "imdb_id": "tt100",
                "media_type": "movie",
                "title": "Movie",
                "original_title": "Movie",
                "production_status": "Released",
                "release_date": "2026-01-01",
                "runtime_min": 100,
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "directors": [],
                "creators": [],
                "writers": [],
                "actors": [],
            },
            "series_view": None,
            "watch_providers": [],
            "posters": [],
            "user_data": {
                "watch_state": "to_watch",
                "impression": None,
                "is_collection_pick": None,
                "watch_history": [{
                    "id": 10,
                    "date_earliest": "2026-01-01",
                    "date_latest": "2026-01-01",
                    "created_at": "2026-01-01",
                }],
                "notes": notes,
                "lists": [{"id": 1, "name": "Favorites"}],
            },
        }


if __name__ == "__main__":
    unittest.main()
