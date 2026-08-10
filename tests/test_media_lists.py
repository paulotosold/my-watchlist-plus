import sqlite3
import unittest

import app.media_repository as media_repository
from app.media_user_data.lists import (
    DUPLICATE_LIST_NAME_ERROR,
    EMPTY_LIST_NAME_ERROR,
    is_duplicate_list_name,
    normalize_list_description,
    normalize_list_name,
    validate_list_name,
)
from db.connection import apply_database_schema


class MediaListsDomainTests(unittest.TestCase):
    def test_normalizes_and_validates_list_fields(self):
        self.assertEqual(normalize_list_name("  Kinotag  "), "Kinotag")
        self.assertEqual(validate_list_name("  Kinotag  "), "Kinotag")
        self.assertEqual(
            normalize_list_description("  First line\nSecond line  "),
            "First line\nSecond line",
        )
        self.assertIsNone(normalize_list_description(" \n\t "))

        for value in (None, "", "   ", "\n\t"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError,
                EMPTY_LIST_NAME_ERROR,
            ):
                validate_list_name(value)

    def test_duplicate_name_excludes_the_list_being_edited(self):
        lists = [
            {"id": 1, "name": "Kinotag"},
            {"id": 2, "name": "Favorites"},
        ]

        self.assertTrue(is_duplicate_list_name("Kinotag", lists))
        self.assertFalse(
            is_duplicate_list_name("Kinotag", lists, current_list_id=1)
        )


class MediaListsRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)
        self.media_ids = [
            self.conn.execute(
                "INSERT INTO media (tmdb_id, media_type, title) VALUES (?, 'movie', ?)",
                (index, f"Movie {index}"),
            ).lastrowid
            for index in (1, 2)
        ]

    def tearDown(self):
        self.conn.close()

    def test_create_and_update_list_preserve_memberships(self):
        created = media_repository.create_list(
            self.conn,
            "  Kinotag  ",
            "  Weekly movies  ",
        )

        for media_id in self.media_ids:
            self.conn.execute(
                "INSERT INTO media_lists (media_id, list_id) VALUES (?, ?)",
                (media_id, created["id"]),
            )

        updated = media_repository.update_list(
            self.conn,
            created["id"],
            "  Family cinema  ",
            "  Renamed without changing identity  ",
        )

        self.assertEqual(
            updated,
            {
                "id": created["id"],
                "name": "Family cinema",
                "description": "Renamed without changing identity",
            },
        )
        row = self.conn.execute(
            "SELECT name, description, updated_at FROM lists WHERE id = ?",
            (created["id"],),
        ).fetchone()
        self.assertEqual(row["name"], "Family cinema")
        self.assertEqual(row["description"], "Renamed without changing identity")
        self.assertIsNotNone(row["updated_at"])
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM media_lists WHERE list_id = ?",
                (created["id"],),
            ).fetchone()[0],
            2,
        )

    def test_delete_list_cascades_all_memberships(self):
        created = media_repository.create_list(self.conn, "Delete me")

        for media_id in self.media_ids:
            self.conn.execute(
                "INSERT INTO media_lists (media_id, list_id) VALUES (?, ?)",
                (media_id, created["id"]),
            )

        self.assertTrue(media_repository.delete_list(self.conn, created["id"]))
        self.assertIsNone(
            self.conn.execute(
                "SELECT id FROM lists WHERE id = ?",
                (created["id"],),
            ).fetchone()
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM media_lists WHERE list_id = ?",
                (created["id"],),
            ).fetchone()[0],
            0,
        )
        self.assertFalse(media_repository.delete_list(self.conn, created["id"]))

    def test_list_names_are_unique_and_required(self):
        created = media_repository.create_list(self.conn, "Kinotag")

        with self.assertRaisesRegex(ValueError, DUPLICATE_LIST_NAME_ERROR):
            media_repository.create_list(self.conn, "Kinotag")

        other = media_repository.create_list(self.conn, "Favorites")

        with self.assertRaisesRegex(ValueError, DUPLICATE_LIST_NAME_ERROR):
            media_repository.update_list(
                self.conn,
                other["id"],
                created["name"],
            )

        with self.assertRaisesRegex(ValueError, EMPTY_LIST_NAME_ERROR):
            media_repository.create_list(self.conn, " \n\t ")

    def test_get_all_lists_uses_case_insensitive_alphabetical_order(self):
        for name in ("zeta", "Alpha", "beta"):
            media_repository.create_list(self.conn, name)

        self.assertEqual(
            [item["name"] for item in media_repository.get_all_lists(self.conn)],
            ["Alpha", "beta", "zeta"],
        )


if __name__ == "__main__":
    unittest.main()
