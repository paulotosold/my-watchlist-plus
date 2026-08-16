from copy import deepcopy
import sqlite3
import unittest

import app.media_repository as media_repository
from app.media_draft import saver as draft_saver
from db.connection import apply_database_schema


class CabinetStateTransitionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_full_draft_save_assigns_max_plus_one_and_clears_on_exit(self):
        first = self._draft(1, worthy=True, cabinet_order=999)
        second = self._draft(2, worthy=True)
        first_id = media_repository.save_media_draft(self.conn, first)
        second_id = media_repository.save_media_draft(self.conn, second)

        self.assertEqual(first["user_data"]["cabinet_order"], 1)
        self.assertEqual(second["user_data"]["cabinet_order"], 2)

        first["user_data"]["is_cabinet_worthy"] = False
        media_repository.save_media_draft(self.conn, first)
        self.assertIsNone(self._state(first_id)["cabinet_order"])

        first["user_data"]["is_cabinet_worthy"] = True
        media_repository.save_media_draft(self.conn, first)
        self.assertEqual(self._state(first_id)["cabinet_order"], 3)
        self.assertEqual(self._state(second_id)["cabinet_order"], 2)

    def test_true_to_true_preserves_null_order_before_initialization(self):
        draft = self._draft(10, worthy=True)
        media_id = media_repository.save_media_draft(self.conn, draft)
        self.conn.execute(
            "UPDATE media_state SET cabinet_order = NULL WHERE media_id = ?",
            (media_id,),
        )
        draft["user_data"]["cabinet_order"] = 200

        media_repository.save_media_draft(self.conn, draft)

        self.assertIsNone(self._state(media_id)["cabinet_order"])
        self.assertIsNone(draft["user_data"]["cabinet_order"])

    def test_inline_patch_returns_and_persists_canonical_order(self):
        existing = self._draft(20, worthy=True)
        media_repository.save_media_draft(self.conn, existing)
        media_id = self._insert_media(21, "Candidate")

        created = media_repository.apply_media_state_patch(
            self.conn,
            media_id,
            expected_values={"is_cabinet_worthy": None},
            changes={"is_cabinet_worthy": True},
        )
        self.assertEqual(created["cabinet_order"], 2)

        cleared = media_repository.apply_media_state_patch(
            self.conn,
            media_id,
            expected_values={"is_cabinet_worthy": True},
            changes={"is_cabinet_worthy": False},
        )
        self.assertIsNone(cleared["cabinet_order"])

    def test_incremental_save_returns_canonical_state_without_trusting_draft(self):
        draft = self._draft(30, worthy=False)
        media_id = media_repository.save_media_draft(self.conn, draft)
        baseline = deepcopy(draft)
        current = deepcopy(draft)
        current["user_data"]["is_cabinet_worthy"] = True
        current["user_data"]["cabinet_order"] = 500

        result = media_repository.apply_media_user_changes(
            self.conn,
            media_id,
            baseline,
            current,
        )

        self.assertEqual(result["media_state"]["cabinet_order"], 1)
        self.assertEqual(self._state(media_id)["cabinet_order"], 1)
        self.assertEqual(current["user_data"]["cabinet_order"], 500)

    def test_unrelated_state_edits_do_not_write_cabinet_order(self):
        draft = self._draft(40, worthy=True)
        media_id = media_repository.save_media_draft(self.conn, draft)
        self.conn.execute(
            f"""
            CREATE TRIGGER reject_order_write_for_unrelated_edit
            BEFORE UPDATE OF cabinet_order ON media_state
            WHEN OLD.media_id = {media_id}
            BEGIN
                SELECT RAISE(ABORT, 'cabinet order must not be written');
            END
            """
        )

        state = media_repository.apply_media_state_patch(
            self.conn,
            media_id,
            expected_values={"impression": None},
            changes={"impression": "good"},
        )

        self.assertEqual(state["impression"], "good")
        self.assertEqual(state["cabinet_order"], 1)

    def test_draft_saver_result_includes_canonical_order(self):
        draft = self._draft(50, worthy=True, cabinet_order=700)

        result = draft_saver.save_media_draft_with_posters(
            self.conn,
            draft,
        )

        self.assertEqual(result["media_state"]["cabinet_order"], 1)
        self.assertEqual(draft["user_data"]["cabinet_order"], 1)

    def _draft(self, tmdb_id, *, worthy, cabinet_order=None):
        return {
            "media_id": None,
            "metadata": {
                "tmdb_id": tmdb_id,
                "media_type": "movie",
                "title": f"Media {tmdb_id}",
            },
            "series_view": None,
            "watch_providers": [],
            "posters": [],
            "user_data": {
                "watch_state": "to_watch",
                "impression": None,
                "is_cabinet_worthy": worthy,
                "cabinet_order": cabinet_order,
                "watch_history": [],
                "notes": [],
                "lists": [],
            },
        }

    def _insert_media(self, tmdb_id, title):
        return self.conn.execute(
            "INSERT INTO media (tmdb_id, media_type, title) VALUES (?, 'movie', ?)",
            (tmdb_id, title),
        ).lastrowid

    def _state(self, media_id):
        return dict(self.conn.execute(
            """
            SELECT is_cabinet_worthy, cabinet_order
            FROM media_state
            WHERE media_id = ?
            """,
            (media_id,),
        ).fetchone())


if __name__ == "__main__":
    unittest.main()
