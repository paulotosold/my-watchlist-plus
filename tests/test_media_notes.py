import copy
import sqlite3
import unittest

import app.media_repository as media_repository
from app.media_notes import (
    EMPTY_NOTE_ERROR,
    apply_note_result,
    normalize_note_text,
    validate_note_text,
)
from db.connection import apply_database_schema


class MediaNotesDomainTests(unittest.TestCase):
    def test_normalizes_and_validates_note_text(self):
        self.assertEqual(
            normalize_note_text("  first line\nsecond line  "),
            "first line\nsecond line",
        )
        self.assertEqual(
            validate_note_text("  first line\nsecond line  "),
            "first line\nsecond line",
        )

        for value in (None, "", "   ", "\t\n\r"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError,
                EMPTY_NOTE_ERROR,
            ):
                validate_note_text(value)

    def test_add_appends_a_normalized_note_with_draft_id(self):
        draft = {
            "user_data": {
                "notes": [{"id": 1, "note": "Older"}],
            },
        }

        apply_note_result(
            draft,
            None,
            {"action": "save", "note": "  Newer\nline  "},
        )

        notes = draft["user_data"]["notes"]
        self.assertEqual(notes[0], {"id": 1, "note": "Older"})
        self.assertEqual(notes[1]["note"], "Newer\nline")
        self.assertTrue(notes[1]["draft_id"])

    def test_edit_preserves_identity_creation_time_and_position(self):
        notes = [
            {
                "id": 1,
                "note": "Duplicate",
                "created_at": "2026-01-01 10:00:00",
            },
            {
                "id": 2,
                "note": "Duplicate",
                "created_at": "2026-01-02 10:00:00",
            },
        ]
        draft = {"user_data": {"notes": copy.deepcopy(notes)}}
        entry = {**notes[1], "note_index": 1}

        apply_note_result(
            draft,
            entry,
            {"action": "save", "note": "Edited"},
        )

        self.assertEqual(draft["user_data"]["notes"][0], notes[0])
        self.assertEqual(
            draft["user_data"]["notes"][1],
            {
                "id": 2,
                "note": "Edited",
                "created_at": "2026-01-02 10:00:00",
            },
        )

    def test_delete_uses_the_captured_index_for_duplicate_text(self):
        draft = {
            "user_data": {
                "notes": [
                    {"id": 1, "note": "Duplicate"},
                    {"id": 2, "note": "Duplicate"},
                ],
            },
        }

        apply_note_result(
            draft,
            {"id": 2, "note": "Duplicate", "note_index": 1},
            {"action": "delete"},
        )

        self.assertEqual(
            draft["user_data"]["notes"],
            [{"id": 1, "note": "Duplicate"}],
        )


class MediaNotesRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)
        self.media_id = self.conn.execute(
            "INSERT INTO media (tmdb_id, media_type, title) VALUES (1, 'movie', 'Movie')"
        ).lastrowid

    def tearDown(self):
        self.conn.close()

    def test_sqlite_rejects_blank_insert_and_update(self):
        for value in ("", "   ", "\t", "\n", " \t\r\n "):
            with self.subTest(operation="insert", value=repr(value)):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(
                        "INSERT INTO media_notes (media_id, note) VALUES (?, ?)",
                        (self.media_id, value),
                    )

        note_id = self.conn.execute(
            "INSERT INTO media_notes (media_id, note) VALUES (?, ?)",
            (self.media_id, "Valid"),
        ).lastrowid

        for value in ("", "   ", "\t\n"):
            with self.subTest(operation="update", value=repr(value)):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(
                        "UPDATE media_notes SET note = ? WHERE id = ?",
                        (value, note_id),
                    )

        self.conn.execute(
            "UPDATE media_notes SET note = ? WHERE id = ?",
            ("First line\nSecond line", note_id),
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT note FROM media_notes WHERE id = ?",
                (note_id,),
            ).fetchone()["note"],
            "First line\nSecond line",
        )

    def test_schema_recreates_guards_for_an_existing_table(self):
        self.conn.execute("DROP TRIGGER trg_media_notes_validate_insert")
        self.conn.execute("DROP TRIGGER trg_media_notes_validate_update")

        apply_database_schema(self.conn)

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO media_notes (media_id, note) VALUES (?, '')",
                (self.media_id,),
            )

    def test_incremental_save_inserts_updates_and_deletes_notes(self):
        update_id = self._insert_note("Update me")
        delete_id = self._insert_note("Delete me")
        baseline = self._draft([
            {"id": update_id, "note": "Update me"},
            {"id": delete_id, "note": "Delete me"},
        ])
        current = copy.deepcopy(baseline)
        current["user_data"]["notes"] = [
            {"id": update_id, "note": "Updated"},
            {"draft_id": "new-note", "note": "Inserted"},
        ]

        result = media_repository.apply_media_user_changes(
            self.conn,
            self.media_id,
            baseline,
            current,
        )

        new_id = result["inserted_ids_by_draft_id"]["notes"]["new-note"]
        rows = {
            row["id"]: row["note"]
            for row in self.conn.execute(
                "SELECT id, note FROM media_notes WHERE media_id = ?",
                (self.media_id,),
            ).fetchall()
        }
        self.assertEqual(rows, {update_id: "Updated", new_id: "Inserted"})
        self.assertNotIn(delete_id, rows)
        self.assertEqual(result["counts"]["notes_inserted"], 1)
        self.assertEqual(result["counts"]["notes_updated"], 1)
        self.assertEqual(result["counts"]["notes_deleted"], 1)

    def test_incremental_save_rejects_blank_note_before_sql(self):
        baseline = self._draft([])
        current = copy.deepcopy(baseline)
        current["user_data"]["notes"] = [
            {"draft_id": "blank", "note": " \n\t "},
        ]

        with self.assertRaisesRegex(ValueError, EMPTY_NOTE_ERROR):
            media_repository.apply_media_user_changes(
                self.conn,
                self.media_id,
                baseline,
                current,
            )

    def test_incremental_save_detects_concurrent_note_edit(self):
        note_id = self._insert_note("Baseline")
        baseline = self._draft([{"id": note_id, "note": "Baseline"}])
        current = copy.deepcopy(baseline)
        current["user_data"]["notes"][0]["note"] = "Local"
        self.conn.execute(
            "UPDATE media_notes SET note = 'Concurrent' WHERE id = ?",
            (note_id,),
        )

        with self.assertRaises(media_repository.ConcurrentEditError):
            media_repository.apply_media_user_changes(
                self.conn,
                self.media_id,
                baseline,
                current,
            )

    def _insert_note(self, note):
        return self.conn.execute(
            "INSERT INTO media_notes (media_id, note) VALUES (?, ?)",
            (self.media_id, note),
        ).lastrowid

    def _draft(self, notes):
        return {
            "media_id": self.media_id,
            "metadata": {"tmdb_id": 1, "media_type": "movie"},
            "series_view": None,
            "user_data": {
                **media_repository.get_empty_media_user_data(),
                "notes": copy.deepcopy(notes),
            },
        }


if __name__ == "__main__":
    unittest.main()
