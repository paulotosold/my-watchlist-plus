import sqlite3
import unittest

from app.cabinet.repository import (
    initialize_and_load_cabinet,
    initialize_cabinet_order,
    load_cabinet_drafts,
    persist_cabinet_reorder,
)
from app.media_repository import ConcurrentEditError
from db.connection import apply_database_schema


class CabinetRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_initializes_all_null_orders_newest_first_and_is_idempotent(self):
        older = self._insert_worthy(1, "Older", created_at="2026-01-01 00:00:00")
        same_time_low_id = self._insert_worthy(
            2, "Same low", created_at="2026-02-01 00:00:00"
        )
        same_time_high_id = self._insert_worthy(
            3, "Same high", created_at="2026-02-01 00:00:00"
        )

        self.assertEqual(initialize_cabinet_order(self.conn), 3)
        self.assertEqual(
            self._ordered_state(),
            [(same_time_high_id, 3), (same_time_low_id, 2), (older, 1)],
        )
        self.assertEqual(initialize_cabinet_order(self.conn), 0)
        self.assertEqual(
            self._ordered_state(),
            [(same_time_high_id, 3), (same_time_low_id, 2), (older, 1)],
        )

    def test_appends_null_batch_after_existing_custom_order(self):
        existing = self._insert_worthy(10, "Existing", cabinet_order=50)
        newer = self._insert_worthy(11, "Newer", created_at="2026-03-02 00:00:00")
        older = self._insert_worthy(12, "Older", created_at="2026-03-01 00:00:00")

        initialize_cabinet_order(self.conn)

        self.assertEqual(
            self._ordered_state(),
            [(existing, 50), (newer, 49), (older, 48)],
        )

    def test_load_filters_worthy_and_uses_cabinet_order_only(self):
        first = self._insert_worthy(20, "First", cabinet_order=9)
        second = self._insert_worthy(21, "Second", cabinet_order=4)
        excluded = self._insert_media(22, "Excluded")
        self.conn.execute(
            "INSERT INTO media_state (media_id, is_cabinet_worthy) VALUES (?, 0)",
            (excluded,),
        )

        drafts = load_cabinet_drafts(self.conn)

        self.assertEqual([draft["media_id"] for draft in drafts], [first, second])
        self.assertEqual(
            [draft["user_data"]["cabinet_order"] for draft in drafts],
            [9, 4],
        )

    def test_initialize_and_load_is_one_transaction(self):
        first = self._insert_worthy(30, "First", created_at="2026-01-02 00:00:00")
        second = self._insert_worthy(31, "Second", created_at="2026-01-01 00:00:00")
        self.conn.commit()

        drafts = initialize_and_load_cabinet(self.conn)

        self.assertEqual([draft["media_id"] for draft in drafts], [first, second])
        self.assertFalse(self.conn.in_transaction)

    def test_reorder_normalizes_descending_and_persists_between_loads(self):
        media_ids = [
            self._insert_worthy(40 + index, f"Media {index}", cabinet_order=3 - index)
            for index in range(3)
        ]
        self.conn.commit()
        desired = [media_ids[2], media_ids[0], media_ids[1]]

        result = persist_cabinet_reorder(self.conn, media_ids, desired)

        self.assertEqual(result["orders"], {
            desired[0]: 3,
            desired[1]: 2,
            desired[2]: 1,
        })
        self.assertEqual(result["updated_count"], 3)
        self.assertEqual(
            [draft["media_id"] for draft in load_cabinet_drafts(self.conn)],
            desired,
        )

        unchanged = persist_cabinet_reorder(self.conn, desired, desired)
        self.assertEqual(unchanged["updated_count"], 0)

    def test_reorder_rejects_stale_membership_without_writes(self):
        media_ids = [
            self._insert_worthy(50 + index, f"Media {index}", cabinet_order=2 - index)
            for index in range(2)
        ]
        extra = self._insert_worthy(52, "Extra", cabinet_order=3)
        self.conn.commit()

        with self.assertRaises(ConcurrentEditError):
            persist_cabinet_reorder(self.conn, media_ids, list(reversed(media_ids)))

        self.assertEqual(self._ordered_state(), [(extra, 3), (media_ids[0], 2), (media_ids[1], 1)])
        self.assertFalse(self.conn.in_transaction)

    def test_reorder_rolls_back_all_updates_on_failure(self):
        media_ids = [
            self._insert_worthy(60 + index, f"Media {index}", cabinet_order=3 - index)
            for index in range(3)
        ]
        self.conn.execute(
            f"""
            CREATE TRIGGER reject_last_cabinet_update
            BEFORE UPDATE OF cabinet_order ON media_state
            WHEN OLD.media_id = {media_ids[0]}
            BEGIN
                SELECT RAISE(ABORT, 'forced reorder failure');
            END
            """
        )
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            persist_cabinet_reorder(
                self.conn,
                media_ids,
                [media_ids[2], media_ids[1], media_ids[0]],
            )

        self.assertEqual(
            self._ordered_state(),
            [(media_ids[0], 3), (media_ids[1], 2), (media_ids[2], 1)],
        )

    def _insert_media(self, tmdb_id, title):
        return self.conn.execute(
            "INSERT INTO media (tmdb_id, media_type, title) VALUES (?, 'movie', ?)",
            (tmdb_id, title),
        ).lastrowid

    def _insert_worthy(self, tmdb_id, title, *, cabinet_order=None, created_at=None):
        media_id = self._insert_media(tmdb_id, title)
        self.conn.execute(
            """
            INSERT INTO media_state (
                media_id, is_cabinet_worthy, cabinet_order, created_at
            )
            VALUES (?, 1, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (media_id, cabinet_order, created_at),
        )
        return media_id

    def _ordered_state(self):
        return [
            (row["media_id"], row["cabinet_order"])
            for row in self.conn.execute(
                """
                SELECT media_id, cabinet_order
                FROM media_state
                WHERE is_cabinet_worthy IS 1
                ORDER BY cabinet_order DESC
                """
            ).fetchall()
        ]


if __name__ == "__main__":
    unittest.main()
