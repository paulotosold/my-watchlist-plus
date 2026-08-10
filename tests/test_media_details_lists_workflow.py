import os
import sqlite3
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QObject, QPoint, Signal, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
)

from app.media_details.dialog import (
    ENTRY_ACTION_LINE_HEIGHT,
    LIST_CHECKBOX_SIZE,
    LIST_CHECKBOX_TO_TEXT_SPACING,
    MediaDetailsDialog,
)
from app.ui.clickable_entry_label import ClickableEntryLabel
from db.connection import apply_database_schema


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


class MediaDetailsListsWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)
        self.media_id = self._insert_media(1, "Movie")
        self.other_media_id = self._insert_media(2, "Other Movie")
        self.alpha_id = self._insert_list("alpha", "First")
        self.zulu_id = self._insert_list("Zulu", "Last")

        for media_id in (self.media_id, self.other_media_id):
            self.conn.execute(
                "INSERT INTO media_lists (media_id, list_id) VALUES (?, ?)",
                (media_id, self.alpha_id),
            )

        self.connection_patch = patch(
            "app.media_details.dialog.get_connection",
            return_value=self.conn,
        )
        self.connection_patch.start()
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()

        self.connection_patch.stop()
        self.conn.close()
        self.application.processEvents()

    def test_rows_are_alphabetical_with_checkbox_and_clickable_name(self):
        self._insert_list("Beta", None)
        dialog = self._dialog()

        rows = self._list_rows(dialog)
        self.assertEqual([row["name"] for row in rows], ["alpha", "Beta", "Zulu"])

        dialog.show()
        self.application.processEvents()

        for row in rows:
            with self.subTest(name=row["name"]):
                self.assertIsInstance(row["checkbox"], QCheckBox)
                self.assertIsInstance(row["label"], ClickableEntryLabel)
                self.assertEqual(row["label"].textFormat(), Qt.TextFormat.PlainText)
                self.assertEqual(
                    row["checkbox"].size(),
                    QSize(LIST_CHECKBOX_SIZE, LIST_CHECKBOX_SIZE),
                )
                self.assertEqual(
                    row["widget"].height(),
                    ENTRY_ACTION_LINE_HEIGHT,
                )
                self.assertEqual(
                    row["widget"].height(),
                    dialog.watch_history_layout.itemAt(1).widget().height(),
                )
                self.assertGreaterEqual(
                    row["label"].geometry().left()
                    - row["checkbox"].geometry().right()
                    - 1,
                    LIST_CHECKBOX_TO_TEXT_SPACING,
                )

        expected_row_step = (
            ENTRY_ACTION_LINE_HEIGHT + dialog.lists_layout.spacing()
        )
        self.assertEqual(
            [
                rows[index + 1]["widget"].y() - rows[index]["widget"].y()
                for index in range(len(rows) - 1)
            ],
            [expected_row_step] * (len(rows) - 1),
        )

        self.assertTrue(rows[0]["checkbox"].isChecked())
        self.assertFalse(rows[1]["checkbox"].isChecked())
        self.assertFalse(rows[2]["checkbox"].isChecked())

    def test_clicking_name_opens_details_without_toggling_checkbox(self):
        dialog = self._dialog()
        dialog.show()
        self.application.processEvents()
        row = next(
            row for row in self._list_rows(dialog) if row["name"] == "alpha"
        )
        was_checked = row["checkbox"].isChecked()

        with patch(
            "app.media_details.dialog.ListDetailsDialog",
        ) as list_dialog:
            list_dialog.return_value.exec.return_value = QDialog.Rejected
            QTest.mouseClick(
                row["label"],
                Qt.MouseButton.LeftButton,
                pos=QPoint(2, row["label"].height() // 2),
            )

            self.assertEqual(list_dialog.call_count, 1)
            self.assertEqual(
                list_dialog.call_args.args[1]["id"],
                self.alpha_id,
            )
            self.assertEqual(row["checkbox"].isChecked(), was_checked)

            QTest.mouseClick(
                row["checkbox"],
                Qt.MouseButton.LeftButton,
                pos=row["checkbox"].rect().center(),
            )

            self.assertEqual(list_dialog.call_count, 1)
            self.assertNotEqual(row["checkbox"].isChecked(), was_checked)

    def test_create_is_immediate_unchecked_and_preserves_pending_membership(self):
        dialog = self._dialog()
        rows = {row["name"]: row for row in self._list_rows(dialog)}
        rows["Zulu"]["checkbox"].setChecked(True)
        self.assertTrue(dialog._is_dirty)

        with patch(
            "app.media_details.dialog.ListDetailsDialog",
        ) as list_dialog:
            list_dialog.return_value.exec.return_value = QDialog.Accepted
            list_dialog.return_value.result_payload = {
                "action": "save",
                "name": "Beta",
                "description": "Created globally",
            }
            dialog.add_list()

        created = self.conn.execute(
            "SELECT id, description FROM lists WHERE name = 'Beta'"
        ).fetchone()
        self.assertIsNotNone(created)
        self.assertEqual(created["description"], "Created globally")
        rows = {row["name"]: row for row in self._list_rows(dialog)}
        self.assertTrue(rows["alpha"]["checkbox"].isChecked())
        self.assertTrue(rows["Zulu"]["checkbox"].isChecked())
        self.assertFalse(rows["Beta"]["checkbox"].isChecked())
        self.assertEqual(
            [item["id"] for item in dialog.media_draft["user_data"]["lists"]],
            [self.alpha_id, self.zulu_id],
        )

    def test_edit_is_immediate_and_preserves_id_memberships_and_draft_references(self):
        dialog = self._dialog()
        alpha = next(item for item in dialog.all_lists if item["id"] == self.alpha_id)

        with patch(
            "app.media_details.dialog.ListDetailsDialog",
        ) as list_dialog:
            list_dialog.return_value.exec.return_value = QDialog.Accepted
            list_dialog.return_value.result_payload = {
                "action": "save",
                "name": "Family cinema",
                "description": "Renamed",
            }
            dialog.edit_list(alpha)

        row = self.conn.execute(
            "SELECT id, name, description FROM lists WHERE id = ?",
            (self.alpha_id,),
        ).fetchone()
        self.assertEqual(
            dict(row),
            {
                "id": self.alpha_id,
                "name": "Family cinema",
                "description": "Renamed",
            },
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM media_lists WHERE list_id = ?",
                (self.alpha_id,),
            ).fetchone()[0],
            2,
        )

        for draft in (dialog.media_draft, dialog._baseline_media_draft):
            self.assertEqual(
                draft["user_data"]["lists"],
                [{"id": self.alpha_id, "name": "Family cinema"}],
            )

        self.assertEqual(
            [row["name"] for row in self._list_rows(dialog)],
            ["Family cinema", "Zulu"],
        )
        self.assertFalse(dialog._is_dirty)

    def test_delete_is_immediate_and_removes_all_memberships_and_references(self):
        dialog = self._dialog()
        alpha = next(item for item in dialog.all_lists if item["id"] == self.alpha_id)

        with patch(
            "app.media_details.dialog.ListDetailsDialog",
        ) as list_dialog:
            list_dialog.return_value.exec.return_value = QDialog.Accepted
            list_dialog.return_value.result_payload = {"action": "delete"}
            dialog.edit_list(alpha)

        self.assertIsNone(
            self.conn.execute(
                "SELECT id FROM lists WHERE id = ?",
                (self.alpha_id,),
            ).fetchone()
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM media_lists WHERE list_id = ?",
                (self.alpha_id,),
            ).fetchone()[0],
            0,
        )

        for draft in (dialog.media_draft, dialog._baseline_media_draft):
            self.assertEqual(draft["user_data"]["lists"], [])

        self.assertEqual(
            [row["name"] for row in self._list_rows(dialog)],
            ["Zulu"],
        )
        self.assertFalse(dialog._is_dirty)

    def _dialog(self):
        dialog = MediaDetailsDialog(
            None,
            self._draft(),
            metadata_refresh_manager=FakeRefreshManager(),
        )
        self.dialogs.append(dialog)
        return dialog

    def _list_rows(self, dialog):
        rows = []

        for index in range(1, dialog.lists_layout.count() - 1):
            row_widget = dialog.lists_layout.itemAt(index).widget()
            row_layout = row_widget.layout()
            self.assertEqual(row_layout.count(), 3)
            checkbox = row_layout.itemAt(0).widget()
            label = row_layout.itemAt(2).widget()
            rows.append({
                "name": label.text(),
                "checkbox": checkbox,
                "label": label,
                "layout": row_layout,
                "widget": row_widget,
            })

        return rows

    def _draft(self):
        return {
            "media_id": self.media_id,
            "metadata": {
                "tmdb_id": 1,
                "imdb_id": "tt0000001",
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
                    "id": 1,
                    "date_earliest": "2026-01-01",
                    "date_latest": "2026-01-01",
                    "created_at": "2026-01-01 20:00:00",
                }],
                "notes": [],
                "lists": [{"id": self.alpha_id, "name": "alpha"}],
            },
        }

    def _insert_media(self, tmdb_id, title):
        return self.conn.execute(
            "INSERT INTO media (tmdb_id, media_type, title) VALUES (?, 'movie', ?)",
            (tmdb_id, title),
        ).lastrowid

    def _insert_list(self, name, description):
        return self.conn.execute(
            "INSERT INTO lists (name, description) VALUES (?, ?)",
            (name, description),
        ).lastrowid


if __name__ == "__main__":
    unittest.main()
