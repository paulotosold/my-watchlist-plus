import sqlite3
import unittest

import app.media_repository as media_repository
from db.connection import apply_database_schema


class MediaRepositoryReferenceDataTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)
        self.conn.execute(
            "INSERT INTO countries (code, name) VALUES ('AT', 'Austria')"
        )

    def tearDown(self):
        self.conn.close()

    def test_get_country_name_normalizes_code(self):
        self.assertEqual(
            media_repository.get_country_name(self.conn, " at "),
            "Austria",
        )

    def test_get_country_name_returns_none_for_unknown_or_empty_code(self):
        self.assertIsNone(
            media_repository.get_country_name(self.conn, "ZZ")
        )
        self.assertIsNone(media_repository.get_country_name(self.conn, ""))
        self.assertIsNone(media_repository.get_country_name(self.conn, None))


if __name__ == "__main__":
    unittest.main()
