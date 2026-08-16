import sqlite3
import unittest

import app.media_repository as media_repository
from db.connection import apply_database_schema


class MediaRepositoryWatchStateTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_saving_none_preserves_impression_then_removes_empty_row(self):
        draft = self._movie_draft(
            1,
            self._user_data(watch_state="to_watch", impression="good"),
        )
        media_id = media_repository.save_media_draft(self.conn, draft)

        draft["user_data"]["watch_state"] = None
        media_repository.save_media_draft(self.conn, draft)

        state = self._state(media_id)
        self.assertIsNone(state["watch_state"])
        self.assertEqual(state["impression"], "good")

        media_repository.set_media_watch_state(self.conn, media_id, "watched")
        media_repository.set_media_watch_state(self.conn, media_id, None)
        state = self._state(media_id)
        self.assertIsNone(state["watch_state"])
        self.assertEqual(state["impression"], "good")

        draft["user_data"]["impression"] = None
        media_repository.save_media_draft(self.conn, draft)
        self.assertIsNone(self._state(media_id))

    def test_cabinet_order_is_canonical_and_ignores_draft_numbers(self):
        draft = self._movie_draft(
            2,
            self._user_data(
                watch_state="to_watch",
                is_cabinet_worthy=True,
                cabinet_order=7,
            ),
        )
        media_id = media_repository.save_media_draft(self.conn, draft)

        self.assertEqual(self._state(media_id)["cabinet_order"], 1)
        self.assertEqual(draft["user_data"]["cabinet_order"], 1)

        self.conn.execute(
            "UPDATE media_state SET cabinet_order = 4 WHERE media_id = ?",
            (media_id,),
        )
        loaded = media_repository.get_db_media_user_data(
            self.conn,
            draft["metadata"],
        )
        self.assertEqual(loaded["cabinet_order"], 4)

        loaded["cabinet_order"] = 9
        draft["user_data"] = loaded
        media_repository.save_media_draft(self.conn, draft)

        self.assertEqual(self._state(media_id)["cabinet_order"], 4)

    def test_direct_episode_history_delta_preserves_later_override(self):
        series_id = self._insert_media(10, "series", "Series")
        draft = self._episode_draft(
            series_id,
            tmdb_id=11,
            season_num=1,
            episode_num=1,
            user_data=self._user_data(),
        )
        episode_id = media_repository.save_media_draft(self.conn, draft)
        self.assertIsNone(self._state(episode_id))

        draft["user_data"]["watch_history"] = [
            {
                "date_earliest": "2026-01-01",
                "date_latest": "2026-01-01",
            },
        ]
        media_repository.save_media_draft(self.conn, draft)
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        history = self._history(episode_id)
        self.assertEqual(len(history), 1)
        history_id = history[0]["id"]

        draft["user_data"]["watch_state"] = "to_watch"
        draft["user_data"]["watch_history"] = [
            {
                "id": history_id,
                "date_earliest": "2026-02-01",
                "date_latest": "2026-02-02",
            },
        ]
        media_repository.save_media_draft(self.conn, draft)

        self.assertEqual(self._state(episode_id)["watch_state"], "to_watch")
        edited_history = self._history(episode_id)
        self.assertEqual([row["id"] for row in edited_history], [history_id])
        self.assertEqual(edited_history[0]["date_earliest"], "2026-02-01")

        draft["user_data"]["watch_history"] = []
        media_repository.save_media_draft(self.conn, draft)
        self.assertEqual(self._state(episode_id)["watch_state"], "to_watch")

    def test_watched_episode_without_history_creates_one_idempotent_unknown_event(self):
        series_id = self._insert_media(15, "series", "Series")
        draft = self._episode_draft(
            series_id,
            tmdb_id=16,
            season_num=1,
            episode_num=1,
            user_data=self._user_data(watch_state="watched"),
        )

        episode_id = media_repository.save_media_draft(self.conn, draft)
        first_history = self._history(episode_id)
        self.assertEqual(len(first_history), 1)
        self.assertIsNone(first_history[0]["date_earliest"])
        self.assertIsNone(first_history[0]["date_latest"])
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        draft["user_data"] = media_repository.get_db_media_user_data(
            self.conn,
            draft["metadata"],
        )
        media_repository.save_media_draft(self.conn, draft)

        second_history = self._history(episode_id)
        self.assertEqual(len(second_history), 1)
        self.assertEqual(second_history[0]["id"], first_history[0]["id"])
        self.assertIsNone(second_history[0]["date_earliest"])
        self.assertIsNone(second_history[0]["date_latest"])

    def test_repeated_save_of_same_watched_draft_keeps_one_unknown_event(self):
        series_id = self._insert_media(19, "series", "Series")
        draft = self._episode_draft(
            series_id,
            tmdb_id=190,
            season_num=1,
            episode_num=1,
            user_data=self._user_data(watch_state="watched"),
        )

        episode_id = media_repository.save_media_draft(self.conn, draft)
        self.assertEqual(len(draft["user_data"]["watch_history"]), 1)
        first_history_id = draft["user_data"]["watch_history"][0]["id"]
        media_repository.save_media_draft(self.conn, draft)

        history = self._history(episode_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], first_history_id)
        self.assertEqual(
            draft["user_data"]["watch_history"][0]["id"],
            first_history_id,
        )
        self.assertIsNone(history[0]["date_earliest"])
        self.assertIsNone(history[0]["date_latest"])
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

    def test_setting_episode_to_watched_synthesizes_one_unknown_event(self):
        series_id = self._insert_media(191, "series", "Series")
        episode_id = self._insert_episode(series_id, 192, 1, 1)

        media_repository.set_media_watch_state(self.conn, episode_id, "watched")
        media_repository.set_media_watch_state(self.conn, episode_id, "watched")

        history = self._history(episode_id)
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0]["date_earliest"])
        self.assertIsNone(history[0]["date_latest"])
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

    def test_empty_input_deletes_existing_history_without_recreating_it(self):
        series_id = self._insert_media(17, "series", "Series")
        draft = self._episode_draft(
            series_id,
            tmdb_id=18,
            season_num=1,
            episode_num=1,
            user_data=self._user_data(
                watch_history=[{
                    "date_earliest": "2026-02-10",
                    "date_latest": "2026-02-10",
                }],
            ),
        )
        episode_id = media_repository.save_media_draft(self.conn, draft)
        self.assertEqual(len(self._history(episode_id)), 1)
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        draft["user_data"] = self._user_data(
            watch_state=None,
            watch_history=[],
        )
        media_repository.save_media_draft(self.conn, draft)

        self.assertEqual(self._history(episode_id), [])
        self.assertIsNone(self._state(episode_id))

    def test_direct_episode_partial_and_last_history_removal(self):
        series_id = self._insert_media(20, "series", "Series")
        draft = self._episode_draft(
            series_id,
            tmdb_id=21,
            season_num=1,
            episode_num=1,
            user_data=self._user_data(
                watch_history=[
                    {
                        "date_earliest": "2026-03-01",
                        "date_latest": "2026-03-01",
                    },
                    {
                        "date_earliest": "2026-03-02",
                        "date_latest": "2026-03-02",
                    },
                ],
            ),
        )
        episode_id = media_repository.save_media_draft(self.conn, draft)
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        histories = self._history(episode_id)
        draft["user_data"]["watch_state"] = "watched"
        draft["user_data"]["watch_history"] = [dict(histories[1])]
        media_repository.save_media_draft(self.conn, draft)

        self.assertEqual(len(self._history(episode_id)), 1)
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        draft["user_data"]["watch_history"] = []
        media_repository.save_media_draft(self.conn, draft)

        self.assertEqual(self._history(episode_id), [])
        self.assertIsNone(self._state(episode_id))

    def test_series_episode_history_uses_id_deltas_for_state_transitions(self):
        series_id = self._insert_media(30, "series", "Series")
        episode_id = self._insert_episode(series_id, 31, 1, 1)

        first = {
            "episode_id": episode_id,
            "season_num": 1,
            "episode_num": 1,
            "date_earliest": "2026-04-01",
            "date_latest": "2026-04-01",
        }
        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [first],
        )
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        media_repository.set_media_watch_state(self.conn, episode_id, "to_watch")
        first["date_earliest"] = "2026-04-02"
        first["date_latest"] = "2026-04-02"
        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [first],
        )
        self.assertEqual(self._state(episode_id)["watch_state"], "to_watch")

        second = {
            "episode_id": episode_id,
            "season_num": 1,
            "episode_num": 1,
            "date_earliest": "2026-04-03",
            "date_latest": "2026-04-03",
        }
        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [first, second],
        )
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [second],
        )
        self.assertEqual(len(self._history(episode_id)), 1)
        self.assertEqual(self._state(episode_id)["watch_state"], "watched")

        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [],
        )
        self.assertEqual(self._history(episode_id), [])
        self.assertIsNone(self._state(episode_id))

        third = {
            "episode_id": episode_id,
            "season_num": 1,
            "episode_num": 1,
            "date_earliest": "2026-04-04",
            "date_latest": "2026-04-04",
        }
        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [third],
        )
        media_repository.set_media_watch_state(self.conn, episode_id, "to_watch")
        third["date_earliest"] = "2026-04-05"
        third["date_latest"] = "2026-04-05"
        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [third],
        )
        media_repository.sync_series_episode_watch_history(
            self.conn,
            series_id,
            [],
        )
        self.assertEqual(self._state(episode_id)["watch_state"], "to_watch")

    def _movie_draft(self, tmdb_id, user_data):
        return {
            "media_id": None,
            "metadata": {
                "tmdb_id": tmdb_id,
                "media_type": "movie",
                "title": f"Movie {tmdb_id}",
            },
            "watch_providers": [],
            "posters": [],
            "user_data": user_data,
        }

    def _episode_draft(
        self,
        series_id,
        tmdb_id,
        season_num,
        episode_num,
        user_data,
    ):
        series = self.conn.execute(
            "SELECT tmdb_id, title FROM media WHERE id = ?",
            (series_id,),
        ).fetchone()
        return {
            "media_id": None,
            "metadata": {
                "tmdb_id": tmdb_id,
                "media_type": "episode",
                "title": f"Episode {episode_num}",
                "episode_details": {
                    "series_tmdb_id": series["tmdb_id"],
                    "series_title": series["title"],
                    "season_num": season_num,
                    "episode_num": episode_num,
                },
            },
            "watch_providers": [],
            "posters": [],
            "user_data": user_data,
        }

    def _user_data(
        self,
        watch_state=None,
        impression=None,
        is_cabinet_worthy=None,
        cabinet_order=None,
        watch_history=None,
    ):
        return {
            "watch_state": watch_state,
            "impression": impression,
            "is_cabinet_worthy": is_cabinet_worthy,
            "cabinet_order": cabinet_order,
            "watch_history": list(watch_history or []),
            "notes": [],
            "lists": [],
        }

    def _insert_media(self, tmdb_id, media_type, title):
        cursor = self.conn.execute(
            """
            INSERT INTO media (tmdb_id, media_type, title)
            VALUES (?, ?, ?)
            """,
            (tmdb_id, media_type, title),
        )
        return cursor.lastrowid

    def _insert_episode(self, series_id, tmdb_id, season_num, episode_num):
        episode_id = self._insert_media(
            tmdb_id,
            "episode",
            f"Episode {episode_num}",
        )
        self.conn.execute(
            """
            INSERT INTO episode_details (
                media_id,
                series_id,
                season_num,
                episode_num
            )
            VALUES (?, ?, ?, ?)
            """,
            (episode_id, series_id, season_num, episode_num),
        )
        return episode_id

    def _state(self, media_id):
        row = self.conn.execute(
            """
            SELECT
                watch_state,
                impression,
                is_cabinet_worthy,
                cabinet_order
            FROM media_state
            WHERE media_id = ?
            """,
            (media_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def _history(self, media_id):
        return [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT id, date_earliest, date_latest
                FROM watch_history
                WHERE media_id = ?
                ORDER BY id
                """,
                (media_id,),
            ).fetchall()
        ]


if __name__ == "__main__":
    unittest.main()
