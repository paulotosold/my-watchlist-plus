import os
import unittest
from copy import deepcopy
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtWidgets import QApplication, QDialog

from app.media_details_dialog import WatchEntryDetailsDialog
from app.watch_history_editor import apply_watch_entry_result


class WatchEntryDetailsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.application.processEvents()

    def test_new_entry_can_save_immediately_with_empty_dates_and_episodes(self):
        drafts = [
            self._movie_draft(),
            self._series_draft([]),
        ]

        for media_draft in drafts:
            with self.subTest(
                media_type=media_draft["metadata"]["media_type"],
            ):
                dialog = self._dialog(media_draft)

                self.assertTrue(dialog.save_entry_button.isEnabled())
                dialog.save_entry_button.click()

                self.assertEqual(dialog.result(), QDialog.Accepted)
                self.assertEqual(dialog.result_payload["action"], "save")
                self.assertIsNone(dialog.result_payload["date_earliest"])
                self.assertIsNone(dialog.result_payload["date_latest"])
                self.assertEqual(dialog.result_payload["selected_episodes"], [])

    def test_invalid_dates_disable_new_entry_save(self):
        dialog = self._dialog(self._movie_draft())

        dialog.date_earliest_input.setText("2026/05/01")
        self.assertFalse(dialog.save_entry_button.isEnabled())

        dialog.date_earliest_input.clear()
        self.assertTrue(dialog.save_entry_button.isEnabled())

        dialog.date_earliest_input.setText("2026-05-02")
        dialog.date_latest_input.setText("2026-05-01")
        self.assertFalse(dialog.save_entry_button.isEnabled())

    def test_unchanged_edited_entry_stays_disabled_until_valid_change(self):
        entry = {
            "kind": "media_event",
            "watch_history_id": 50,
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
        }
        dialog = self._dialog(self._movie_draft(), entry)

        self.assertFalse(dialog.save_entry_button.isEnabled())

        dialog.date_latest_input.setText("2026-05-02")
        self.assertTrue(dialog.save_entry_button.isEnabled())

        dialog.date_latest_input.setText("invalid")
        self.assertFalse(dialog.save_entry_button.isEnabled())

    def test_episode_selector_filters_by_local_release_date_and_sets_tooltips(self):
        today = date.today()
        episodes = [
            self._episode(11, 1, "Pilot", today - timedelta(days=1)),
            self._episode(12, 2, None, today),
            self._episode(13, 3, "Tomorrow", today + timedelta(days=1)),
            self._episode(14, 4, "Unknown", None),
            self._episode(15, 5, "Malformed", "not-a-date"),
        ]
        dialog = self._dialog(self._series_draft(episodes))

        self.assertEqual(set(dialog.episode_buttons), {(1, 1), (1, 2)})
        self.assertEqual(
            dialog.episode_buttons[(1, 1)][0].toolTip(),
            "Pilot",
        )
        self.assertEqual(
            dialog.episode_buttons[(1, 2)][0].toolTip(),
            "Season 1, Episode 2",
        )

    def test_selected_unavailable_episode_is_locked_and_preserved(self):
        future = date.today() + timedelta(days=30)
        released = self._episode(11, 1, "Released", date.today())
        selected_unavailable = self._episode(13, 3, "Coming Soon", future)
        other_unavailable = self._episode(14, 4, "Later", future)
        selected_row = {
            **deepcopy(selected_unavailable),
            "watch_history_id": 77,
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
        }
        other_row = {
            **deepcopy(other_unavailable),
            "watch_history_id": 78,
            "date_earliest": "2026-05-02",
            "date_latest": "2026-05-02",
        }
        media_draft = self._series_draft(
            [released, selected_unavailable, other_unavailable],
            episode_watch_history=[selected_row, other_row],
        )
        entry = {
            "kind": "episode_group",
            "watch_history_ids": [77],
            "draft_ids": [],
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
            "episodes": [deepcopy(selected_row)],
        }
        dialog = self._dialog(media_draft, entry)

        self.assertEqual(set(dialog.episode_buttons), {(1, 1), (1, 3)})
        selected_button = dialog.episode_buttons[(1, 3)][0]
        self.assertTrue(selected_button.isChecked())
        self.assertFalse(selected_button.isEnabled())
        self.assertIn("Coming Soon", selected_button.toolTip())
        self.assertIn("unavailable", selected_button.toolTip().lower())
        self.assertNotIn((1, 4), dialog.episode_buttons)

        dialog.date_earliest_input.setText("2026-05-03")
        dialog.date_latest_input.setText("2026-05-03")
        self.assertTrue(dialog.save_entry_button.isEnabled())
        dialog.save_entry_button.click()
        apply_watch_entry_result(media_draft, entry, dialog.result_payload)

        rows_by_id = {
            row.get("watch_history_id"): row
            for row in media_draft["series_view"]["episode_watch_history"]
        }
        self.assertEqual(set(rows_by_id), {77, 78})
        self.assertEqual(rows_by_id[77]["season_num"], 1)
        self.assertEqual(rows_by_id[77]["episode_num"], 3)
        self.assertEqual(rows_by_id[77]["date_earliest"], "2026-05-03")

    def _dialog(self, media_draft, entry=None):
        dialog = WatchEntryDetailsDialog(None, media_draft, entry)
        self.addCleanup(dialog.close)
        return dialog

    def _movie_draft(self):
        return {
            "media_id": 1,
            "metadata": {
                "media_type": "movie",
                "title": "Movie",
                "release_date": "2020-01-01",
            },
            "user_data": {"watch_history": []},
        }

    def _series_draft(self, episodes, episode_watch_history=None):
        return {
            "media_id": 10,
            "metadata": {
                "media_type": "series",
                "title": "Series",
                "release_date": "2020-01-01",
            },
            "series_view": {
                "summary": {"first_air_date": "2020-01-01"},
                "episodes": episodes,
                "episode_watch_history": episode_watch_history or [],
            },
            "user_data": {"watch_history": []},
        }

    def _episode(self, episode_id, episode_num, title, release_date):
        return {
            "series_id": 10,
            "episode_id": episode_id,
            "tmdb_id": 1000 + episode_id,
            "season_num": 1,
            "episode_num": episode_num,
            "title": title,
            "release_date": (
                release_date.isoformat()
                if isinstance(release_date, date)
                else release_date
            ),
        }


if __name__ == "__main__":
    unittest.main()
