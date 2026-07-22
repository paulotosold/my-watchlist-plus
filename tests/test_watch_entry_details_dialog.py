import os
import unittest
from copy import deepcopy
from datetime import date, timedelta
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QToolButton

from app.media_details_dialog import WatchEntryDetailsDialog
from app.top_bar import INPUT_BOX_STYLE
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

    def test_new_empty_entry_preview_ranges_from_release_to_today(self):
        today = QDate.currentDate()
        release_date = today.addYears(-2)
        release_text = release_date.toString("yyyy-MM-dd")
        expected_range = f"~{release_date.year()}-{today.year()}"

        movie_draft = self._movie_draft()
        movie_draft["metadata"]["release_date"] = release_text
        series_draft = self._series_draft([])
        series_draft["metadata"]["release_date"] = release_text
        series_draft["series_view"]["summary"]["first_air_date"] = release_text

        cases = (
            (movie_draft, f"Preview: {expected_range}"),
            (
                series_draft,
                f"Preview: {expected_range} · no episode info",
            ),
        )

        for media_draft, expected_preview in cases:
            with self.subTest(
                media_type=media_draft["metadata"]["media_type"],
            ):
                dialog = self._dialog(media_draft)
                self.assertEqual(dialog.preview_label.text(), expected_preview)

    def test_edited_empty_entry_preview_uses_existing_created_at(self):
        today = QDate.currentDate()
        release_date = today.addYears(-6)
        created_date = today.addYears(-3)
        media_draft = self._movie_draft()
        media_draft["metadata"]["release_date"] = release_date.toString(
            "yyyy-MM-dd"
        )
        entry = {
            "kind": "media_event",
            "watch_history_id": 50,
            "date_earliest": None,
            "date_latest": None,
            "created_at": created_date.toString("yyyy-MM-dd"),
        }

        dialog = self._dialog(media_draft, entry)

        self.assertEqual(
            dialog.preview_label.text(),
            f"Preview: ~{release_date.year()}-{created_date.year()}",
        )

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

    def test_smart_fill_uses_label_main_input_style_and_enter(self):
        dialog = self._dialog(self._movie_draft())
        dialog.smart_input.setText("  watched yesterday  ")

        with patch("builtins.print") as print_mock:
            QTest.keyClick(dialog.smart_input, Qt.Key.Key_Return)

        self.assertEqual(dialog.smart_label.text(), "Smart Fill:")
        self.assertEqual(dialog.smart_input.styleSheet(), INPUT_BOX_STYLE)
        self.assertFalse(hasattr(dialog, "smart_button"))
        print_mock.assert_called_once_with("  watched yesterday  ")

    def test_smart_and_date_inputs_use_the_builtin_clear_button(self):
        dialog = self._dialog(self._movie_draft())
        dialog.show()

        for input_widget in (
            dialog.smart_input,
            dialog.date_earliest_input,
            dialog.date_latest_input,
        ):
            with self.subTest(input_widget=input_widget):
                self.assertTrue(input_widget.isClearButtonEnabled())
                input_widget.setText("clear me")
                self.application.processEvents()
                clear_button = input_widget.findChild(QToolButton)

                self.assertIsNotNone(clear_button)
                self.assertTrue(clear_button.isVisible())
                clear_button.click()
                self.assertEqual(input_widget.text(), "")

    def test_inline_date_buttons_have_expected_size_and_icons(self):
        dialog = self._dialog(self._movie_draft())

        for button in (
            dialog.date_earliest_picker_button,
            dialog.copy_date_button,
            dialog.date_latest_picker_button,
        ):
            with self.subTest(tooltip=button.toolTip()):
                self.assertEqual(button.minimumSize(), QSize(32, 32))
                self.assertEqual(button.maximumSize(), QSize(32, 32))
                self.assertEqual(button.iconSize(), QSize(20, 20))
                self.assertFalse(button.icon().isNull())

    def test_copy_over_copies_literal_invalid_and_empty_values(self):
        dialog = self._dialog(self._movie_draft())
        dialog.date_earliest_input.setText("not-a-date")
        dialog.date_latest_input.setText("2026-05-01")

        dialog.copy_date_button.click()

        self.assertEqual(dialog.date_latest_input.text(), "not-a-date")
        self.assertEqual(dialog.error_label.text(), "Use YYYY-MM-DD.")
        self.assertFalse(dialog.error_label.isHidden())
        self.assertFalse(dialog.save_entry_button.isEnabled())

        dialog.date_earliest_input.clear()
        dialog.copy_date_button.click()

        self.assertEqual(dialog.date_latest_input.text(), "")
        self.assertEqual(dialog.error_label.text(), "")
        self.assertTrue(dialog.error_label.isHidden())
        self.assertTrue(dialog.save_entry_button.isEnabled())

    def test_each_date_picker_uses_initial_date_and_updates_its_field(self):
        cases = (
            (
                "earliest",
                "date_earliest_input",
                "date_earliest_picker_button",
                "2026-07-04",
                QDate(2026, 7, 4),
                QDate(2026, 7, 9),
                "date_latest_input",
            ),
            (
                "latest",
                "date_latest_input",
                "date_latest_picker_button",
                "invalid",
                QDate.currentDate(),
                QDate(2026, 8, 3),
                "date_earliest_input",
            ),
        )

        for (
            name,
            input_name,
            button_name,
            initial_text,
            expected_initial_date,
            selected_date,
            other_input_name,
        ) in cases:
            with self.subTest(field=name):
                dialog = self._dialog(self._movie_draft())
                target_input = getattr(dialog, input_name)
                other_input = getattr(dialog, other_input_name)
                picker_button = getattr(dialog, button_name)
                target_input.setText(initial_text)
                other_input.setText("keep-me")
                dialog.show()
                self.application.processEvents()

                picker_button.click()
                self.application.processEvents()
                popup = dialog._date_picker_popup

                self.assertIsNotNone(popup)
                self.assertTrue(popup.isVisible())
                self.assertEqual(popup.current_date, expected_initial_date)

                popup.choose_date(selected_date)

                self.assertEqual(
                    target_input.text(),
                    selected_date.toString("yyyy-MM-dd"),
                )
                self.assertEqual(other_input.text(), "keep-me")
                self.assertIsNone(dialog._date_picker_popup)

                self.application.processEvents()
                self.assertFalse(popup.isVisible())
                dialog.close()

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

    def test_episode_selector_height_tracks_rows_from_the_first_season(self):
        dialog_heights = []

        for season_count in (1, 2, 3):
            episodes = [
                {
                    **self._episode(
                        episode_id=10 + season_num,
                        episode_num=1,
                        title=f"Season {season_num} premiere",
                        release_date=date.today(),
                    ),
                    "season_num": season_num,
                }
                for season_num in range(1, season_count + 1)
            ]
            dialog = self._dialog(self._series_draft(episodes))
            dialog.show()
            self.application.processEvents()
            selector = dialog.findChild(
                QScrollArea,
                "episodeSelectorScroll",
            )

            self.assertIsNotNone(selector)
            self.assertEqual(
                selector.height(),
                selector.widget().sizeHint().height(),
            )
            dialog_heights.append(dialog.height())
            dialog.close()

        self.assertLess(dialog_heights[0], dialog_heights[1])
        self.assertLess(dialog_heights[1], dialog_heights[2])

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
