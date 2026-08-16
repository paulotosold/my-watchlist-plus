import sqlite3
import unittest

from app import media_repository
from app.history import repository as history_repository
from db.connection import apply_database_schema


class HistoryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_default_history_filters_and_groups_without_n_plus_one(self):
        movie_id = self._insert_media(
            1,
            "movie",
            "Movie",
            release_date="2025-01-01",
        )
        self._set_state(
            movie_id,
            watch_state="watched",
            impression="very_good",
            is_cabinet_worthy=True,
        )
        movie_history_id = self._insert_history(
            movie_id,
            "2026-07-05",
            "2026-07-05",
            created_at="2026-07-05 22:00:00",
        )
        self._insert_poster(movie_id, "pending.jpg", "pending")
        self._insert_poster(movie_id, "selected.jpg", "selected")
        self._insert_poster(
            movie_id,
            "default.jpg",
            "selected",
            is_default=True,
        )

        series_id = self._insert_media(
            10,
            "series",
            "Fallout",
            release_date="2024-04-10",
        )
        self._set_state(
            series_id,
            impression="good",
            is_cabinet_worthy=False,
        )
        self._insert_poster(series_id, "fallout.jpg", "selected")
        self._insert_season_poster(
            series_id,
            1,
            "fallout-season-one.jpg",
            "selected",
        )
        episode_1 = self._insert_episode(
            series_id,
            11,
            1,
            1,
            release_date="2024-04-10",
        )
        episode_2 = self._insert_episode(
            series_id,
            12,
            1,
            2,
            release_date="2024-04-10",
        )
        self._set_state(
            episode_1,
            watch_state="watched",
            impression="meh",
            is_cabinet_worthy=True,
        )
        self._set_state(episode_2, watch_state="watched")
        self._insert_poster(
            episode_1,
            "episode-one.jpg",
            "selected",
        )
        first_session_ids = (
            self._insert_history(
                episode_1,
                "2026-07-03",
                "2026-07-03",
                created_at="2026-07-03 19:00:00",
            ),
            self._insert_history(
                episode_2,
                "2026-07-03",
                "2026-07-03",
                created_at="2026-07-03 20:00:00",
            ),
        )
        rewatch_id = self._insert_history(
            episode_1,
            "2026-07-10",
            "2026-07-10",
            created_at="2026-07-10 20:00:00",
        )

        to_watch_id = self._insert_media(20, "movie", "Watch Again")
        self._set_state(to_watch_id, watch_state="to_watch")
        to_watch_history_id = self._insert_history(
            to_watch_id,
            "2026-07-15",
            "2026-07-15",
        )
        history_only_id = self._insert_media(22, "movie", "History Only")
        history_only_history_id = self._insert_history(
            history_only_id,
            "2026-07-16",
            "2026-07-16",
        )
        watched_without_history_id = self._insert_media(
            21,
            "movie",
            "No Entry",
        )
        self._set_state(watched_without_history_id, watch_state="watched")

        statements = []
        self.conn.set_trace_callback(statements.append)
        entries = history_repository.load_default_history_entries(self.conn)
        self.conn.set_trace_callback(None)

        select_statements = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith(("SELECT", "WITH"))
        ]
        self.assertEqual(len(select_statements), 1)
        self.assertEqual(len(entries), 5)

        history_only, to_watch, rewatch, movie, first_session = entries
        self.assertEqual(
            history_only.watch_history_ids,
            (history_only_history_id,),
        )
        self.assertEqual(history_only.title, "History Only")
        self.assertIsNone(history_only.watch_state)

        self.assertEqual(
            to_watch.watch_history_ids,
            (to_watch_history_id,),
        )
        self.assertEqual(to_watch.title, "Watch Again")
        self.assertEqual(to_watch.watch_state, "to_watch")

        self.assertEqual(rewatch.watch_history_ids, (rewatch_id,))
        self.assertEqual(
            rewatch.title,
            "Fallout (S1:E1) – Episode 1",
        )
        self.assertEqual(rewatch.details_media_id, episode_1)
        self.assertEqual(rewatch.state_media_id, episode_1)
        self.assertEqual(rewatch.owner_media_ids, (episode_1,))
        self.assertEqual(rewatch.media_type, "episode")
        self.assertEqual(rewatch.watch_state, "watched")
        self.assertEqual(rewatch.impression, "meh")
        self.assertTrue(rewatch.is_cabinet_worthy)
        self.assertEqual(
            rewatch.poster["filename"],
            "episode-one.jpg",
        )

        self.assertEqual(movie.watch_history_ids, (movie_history_id,))
        self.assertEqual(movie.details_media_id, movie_id)
        self.assertEqual(movie.media_type, "movie")
        self.assertEqual(movie.watch_state, "watched")
        self.assertEqual(movie.formatted_date, "5 Jul 2026, Sun")
        self.assertEqual(movie.poster["filename"], "default.jpg")

        self.assertEqual(
            first_session.watch_history_ids,
            first_session_ids,
        )
        self.assertEqual(first_session.owner_media_ids, (episode_1, episode_2))
        self.assertEqual(first_session.title, "Fallout (S1:E1-2)")
        self.assertEqual(first_session.formatted_date, "3 Jul 2026, Fri")
        self.assertEqual(first_session.details_media_id, series_id)
        self.assertEqual(first_session.state_media_id, series_id)
        self.assertEqual(first_session.media_type, "series")
        self.assertIsNone(first_session.watch_state)
        self.assertEqual(first_session.impression, "good")
        self.assertFalse(first_session.is_cabinet_worthy)
        self.assertEqual(
            first_session.poster["filename"],
            "fallout-season-one.jpg",
        )

    def test_direct_events_use_canonical_descending_tie_breaks(self):
        movie_id = self._insert_media(
            30,
            "movie",
            "Repeated Movie",
            release_date="2020-01-01",
        )
        self._set_state(movie_id, watch_state="watched")
        first_id = self._insert_history(
            movie_id,
            "2026-06-01",
            "2026-06-30",
            created_at="2026-07-01 00:00:00",
        )
        second_id = self._insert_history(
            movie_id,
            "2026-06-20",
            "2026-06-20",
            created_at="2026-07-01 00:00:00",
        )
        third_id = self._insert_history(
            movie_id,
            "2026-06-20",
            "2026-06-20",
            created_at="2026-07-01 00:00:00",
        )

        entries = history_repository.load_default_history_entries(self.conn)

        self.assertEqual(
            [entry.watch_history_ids[0] for entry in entries],
            [third_id, second_id, first_id],
        )
        self.assertEqual(entries[-1].formatted_date, "Jun 2026")

    def test_direct_series_uses_first_air_date_for_ambiguous_dates(self):
        series_id = self._insert_media(
            40,
            "series",
            "Series",
            release_date="2019-01-01",
        )
        self._insert_episode(
            series_id,
            41,
            1,
            1,
            release_date="2024-04-10",
        )
        self._set_state(series_id, watch_state="watched")
        self._insert_history(
            series_id,
            None,
            None,
            created_at="2026-07-01 00:00:00",
        )

        entry = history_repository.load_default_history_entries(self.conn)[0]

        self.assertEqual(entry.kind, "media_event")
        self.assertEqual(entry.title, "Series")
        self.assertEqual(entry.release_date, "2024-04-10")
        self.assertEqual(entry.formatted_date, "~2024-2026")

    def test_episode_group_title_formats_multiple_seasons(self):
        series_id = self._insert_media(
            50,
            "series",
            "Long Series",
            release_date="2020-01-01",
        )
        self._insert_poster(
            series_id,
            "long-series.jpg",
            "selected",
        )
        self._insert_season_poster(
            series_id,
            1,
            "long-series-season-one.jpg",
            "selected",
        )
        self._insert_season_poster(
            series_id,
            2,
            "long-series-season-two.jpg",
            "selected",
        )

        for tmdb_id, season_num, episode_num in (
            (51, 1, 1),
            (52, 1, 2),
            (53, 2, 1),
        ):
            episode_id = self._insert_episode(
                series_id,
                tmdb_id,
                season_num,
                episode_num,
                release_date="2020-01-01",
            )
            self._set_state(episode_id, watch_state="watched")
            self._insert_history(
                episode_id,
                "2026-07-01",
                "2026-07-01",
            )

        entries = history_repository.load_default_history_entries(self.conn)

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0].title,
            "Long Series (S1:E1-2, S2:E1)",
        )
        self.assertEqual(len(entries[0].watch_history_ids), 3)
        self.assertEqual(
            entries[0].poster["filename"],
            "long-series.jpg",
        )

    def test_single_episode_uses_episode_state_and_season_poster_fallback(self):
        series_id = self._insert_media(
            70,
            "series",
            "Black Mirror",
            release_date="2011-12-04",
        )
        self._insert_poster(
            series_id,
            "black-mirror.jpg",
            "pending",
        )
        self._insert_season_poster(
            series_id,
            3,
            "black-mirror-season-three.jpg",
            "selected",
        )
        episode_id = self._insert_episode(
            series_id,
            71,
            3,
            4,
            release_date="2016-10-21",
        )
        self.conn.execute(
            "UPDATE media SET title = 'San Junipero' WHERE id = ?",
            (episode_id,),
        )
        self._set_state(
            episode_id,
            watch_state="watched",
            impression="very_good",
        )
        self._insert_history(
            episode_id,
            "2021-08-03",
            "2021-08-03",
        )

        entry = history_repository.load_default_history_entries(self.conn)[0]

        self.assertEqual(
            entry.title,
            "Black Mirror (S3:E4) – San Junipero",
        )
        self.assertEqual(entry.kind, "episode_event")
        self.assertEqual(entry.state_media_id, episode_id)
        self.assertEqual(entry.details_media_id, episode_id)
        self.assertEqual(entry.impression, "very_good")
        self.assertEqual(
            entry.poster["filename"],
            "black-mirror-season-three.jpg",
        )

    def test_single_episode_falls_back_to_series_without_season_poster(self):
        series_id = self._insert_media(
            80,
            "series",
            "Anthology",
            release_date="2018-01-01",
        )
        self._insert_poster(
            series_id,
            "anthology.jpg",
            "selected",
        )
        episode_id = self._insert_episode(
            series_id,
            81,
            2,
            5,
            release_date="2020-02-05",
        )
        self._set_state(episode_id, watch_state="watched")
        self._insert_history(
            episode_id,
            "2020-02-05",
            "2020-02-05",
        )

        entry = history_repository.load_default_history_entries(self.conn)[0]

        self.assertEqual(
            entry.poster["filename"],
            "anthology.jpg",
        )

    def test_orphan_episodes_remain_independent_direct_entries(self):
        orphan_ids = []

        for tmdb_id, title in (
            (60, "Orphan One"),
            (61, "Orphan Two"),
        ):
            media_id = self._insert_media(
                tmdb_id,
                "episode",
                title,
                release_date="2025-01-01",
            )
            orphan_ids.append(media_id)
            self._set_state(media_id, watch_state="watched")
            self._insert_history(
                media_id,
                "2026-07-01",
                "2026-07-01",
            )

        entries = history_repository.load_default_history_entries(self.conn)

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {entry.title for entry in entries},
            {"Orphan One", "Orphan Two"},
        )
        self.assertEqual(
            {entry.details_media_id for entry in entries},
            set(orphan_ids),
        )
        self.assertTrue(all(entry.kind == "media_event" for entry in entries))

    def _insert_media(
        self,
        tmdb_id,
        media_type,
        title,
        release_date=None,
    ):
        return self.conn.execute(
            """
            INSERT INTO media (tmdb_id, media_type, title, release_date)
            VALUES (?, ?, ?, ?)
            """,
            (tmdb_id, media_type, title, release_date),
        ).lastrowid

    def _insert_episode(
        self,
        series_id,
        tmdb_id,
        season_num,
        episode_num,
        release_date=None,
    ):
        episode_id = self._insert_media(
            tmdb_id,
            "episode",
            f"Episode {episode_num}",
            release_date=release_date,
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

    def _set_state(
        self,
        media_id,
        watch_state=None,
        impression=None,
        is_cabinet_worthy=None,
    ):
        self.conn.execute(
            """
            INSERT INTO media_state (
                media_id,
                watch_state,
                impression,
                is_cabinet_worthy
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                media_id,
                watch_state,
                impression,
                (
                    None
                    if is_cabinet_worthy is None
                    else int(is_cabinet_worthy)
                ),
            ),
        )

    def _insert_history(
        self,
        media_id,
        date_earliest,
        date_latest,
        created_at=None,
    ):
        if created_at is None:
            return self.conn.execute(
                """
                INSERT INTO watch_history (
                    media_id,
                    date_earliest,
                    date_latest
                )
                VALUES (?, ?, ?)
                """,
                (media_id, date_earliest, date_latest),
            ).lastrowid

        return self.conn.execute(
            """
            INSERT INTO watch_history (
                media_id,
                date_earliest,
                date_latest,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (media_id, date_earliest, date_latest, created_at),
        ).lastrowid

    def _insert_poster(
        self,
        media_id,
        filename,
        curation_status,
        is_default=False,
    ):
        self.conn.execute(
            """
            INSERT INTO media_posters (
                media_id,
                filename,
                source,
                curation_status,
                is_default
            )
            VALUES (?, ?, 'tmdb', ?, ?)
            """,
            (media_id, filename, curation_status, int(is_default)),
        )

    def _insert_season_poster(
        self,
        series_id,
        season_num,
        filename,
        curation_status,
        is_default=False,
    ):
        self.conn.execute(
            """
            INSERT INTO season_posters (
                series_id,
                season_num,
                filename,
                source,
                curation_status,
                is_default
            )
            VALUES (?, ?, ?, 'tmdb', ?, ?)
            """,
            (
                series_id,
                season_num,
                filename,
                curation_status,
                int(is_default),
            ),
        )


class MediaStatePatchTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        apply_database_schema(self.conn)
        self.media_id = self.conn.execute(
            """
            INSERT INTO media (tmdb_id, media_type, title)
            VALUES (100, 'movie', 'Movie')
            """
        ).lastrowid
        self.conn.execute(
            """
            INSERT INTO media_state (
                media_id,
                watch_state,
                impression,
                is_cabinet_worthy
            )
            VALUES (?, 'watched', 'good', 0)
            """,
            (self.media_id,),
        )

    def tearDown(self):
        self.conn.close()

    def test_patch_preserves_watch_state_and_other_editable_field(self):
        state = media_repository.apply_media_state_patch(
            self.conn,
            self.media_id,
            expected_values={"impression": "good"},
            changes={"impression": "very_good"},
        )

        self.assertEqual(state, {
            "media_id": self.media_id,
            "watch_state": "watched",
            "impression": "very_good",
            "is_cabinet_worthy": False,
        })

    def test_patch_is_idempotent_when_desired_value_is_already_current(self):
        state = media_repository.apply_media_state_patch(
            self.conn,
            self.media_id,
            expected_values={"impression": None},
            changes={"impression": "good"},
        )

        self.assertEqual(state["impression"], "good")

    def test_patch_updates_watch_state_directly(self):
        state = media_repository.apply_media_state_patch(
            self.conn,
            self.media_id,
            expected_values={"watch_state": "watched"},
            changes={"watch_state": "to_watch"},
        )

        self.assertEqual(state["watch_state"], "to_watch")
        self.assertEqual(state["impression"], "good")
        self.assertFalse(state["is_cabinet_worthy"])
        self.assertEqual(
            self.conn.execute(
                "SELECT watch_state FROM media_state WHERE media_id = ?",
                (self.media_id,),
            ).fetchone()["watch_state"],
            "to_watch",
        )

    def test_patch_rejects_watch_state_not_supported_by_media_type(self):
        with self.assertRaises(ValueError):
            media_repository.apply_media_state_patch(
                self.conn,
                self.media_id,
                expected_values={"watch_state": "watched"},
                changes={"watch_state": "dropped"},
            )

    def test_patch_detects_same_field_conflict(self):
        self.conn.execute(
            "UPDATE media_state SET impression = 'meh' WHERE media_id = ?",
            (self.media_id,),
        )

        with self.assertRaises(media_repository.ConcurrentEditError):
            media_repository.apply_media_state_patch(
                self.conn,
                self.media_id,
                expected_values={"impression": "good"},
                changes={"impression": "very_good"},
            )

        state = media_repository.get_media_state(self.conn, self.media_id)
        self.assertEqual(state["impression"], "meh")
        self.assertEqual(state["watch_state"], "watched")

    def test_patch_can_create_and_remove_a_state_row(self):
        media_id = self.conn.execute(
            """
            INSERT INTO media (tmdb_id, media_type, title)
            VALUES (101, 'series', 'Series')
            """
        ).lastrowid

        created = media_repository.apply_media_state_patch(
            self.conn,
            media_id,
            expected_values={"is_cabinet_worthy": None},
            changes={"is_cabinet_worthy": True},
        )
        self.assertTrue(created["is_cabinet_worthy"])

        cleared = media_repository.apply_media_state_patch(
            self.conn,
            media_id,
            expected_values={"is_cabinet_worthy": True},
            changes={"is_cabinet_worthy": None},
        )
        self.assertEqual(cleared, {
            "media_id": media_id,
            "watch_state": None,
            "impression": None,
            "is_cabinet_worthy": None,
        })
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM media_state WHERE media_id = ?",
            (media_id,),
        ).fetchone())

    def test_patch_rejects_invalid_cabinet_worthy_value(self):
        for expected, desired in (
            (False, "yes"),
            ("false", True),
        ):
            with self.subTest(expected=expected, desired=desired):
                with self.assertRaises(ValueError):
                    media_repository.apply_media_state_patch(
                        self.conn,
                        self.media_id,
                        expected_values={
                            "is_cabinet_worthy": expected,
                        },
                        changes={"is_cabinet_worthy": desired},
                    )

    def test_patch_update_predicate_closes_the_concurrent_write_window(self):
        class RacingConnection:
            def __init__(self, connection):
                self.connection = connection
                self.injected_race = False

            def execute(self, statement, parameters=()):
                normalized = " ".join(statement.split()).upper()

                if (
                    normalized.startswith("UPDATE MEDIA_STATE SET IMPRESSION")
                    and "AND IMPRESSION IS ?" in normalized
                    and not self.injected_race
                ):
                    self.injected_race = True
                    self.connection.execute(
                        """
                        UPDATE media_state
                        SET impression = 'meh'
                        WHERE media_id = ?
                        """,
                        (self.media_id,),
                    )

                return self.connection.execute(statement, parameters)

        racing_connection = RacingConnection(self.conn)
        racing_connection.media_id = self.media_id

        with self.assertRaises(media_repository.ConcurrentEditError):
            media_repository.apply_media_state_patch(
                racing_connection,
                self.media_id,
                expected_values={"impression": "good"},
                changes={"impression": "very_good"},
            )

        state = media_repository.get_media_state(self.conn, self.media_id)
        self.assertEqual(state["impression"], "meh")


if __name__ == "__main__":
    unittest.main()
