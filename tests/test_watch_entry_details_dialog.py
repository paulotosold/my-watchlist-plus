import os
import unittest
from copy import deepcopy
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QDate, QPoint, QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QScrollArea,
    QToolButton,
)

from app.media_details.watch_entry_dialog import WatchEntryDetailsDialog
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

    def test_date_validation_updates_exact_preview_without_error_line(self):
        dialog = self._dialog(self._movie_draft())
        expected_empty_preview = (
            f"Preview: ~2020-{QDate.currentDate().year()}"
        )

        self.assertFalse(hasattr(dialog, "error_label"))
        self.assertEqual(dialog.preview_label.text(), expected_empty_preview)

        dialog.date_earliest_input.setText("2026/05/01")
        self.assertFalse(dialog.save_entry_button.isEnabled())
        self.assertEqual(
            dialog.preview_label.text(),
            "Preview: Invalid date — use YYYY-MM-DD",
        )
        self.assertEqual(
            dialog.preview_label.palette()
            .color(QPalette.ColorRole.WindowText)
            .name(),
            "#000000",
        )

        dialog.date_earliest_input.clear()
        self.assertTrue(dialog.save_entry_button.isEnabled())
        self.assertEqual(dialog.preview_label.text(), expected_empty_preview)

        dialog.date_earliest_input.setText("2026-05-02")
        dialog.date_latest_input.setText("2026-05-01")
        self.assertFalse(dialog.save_entry_button.isEnabled())
        self.assertEqual(
            dialog.preview_label.text(),
            "Preview: Invalid range — check date order",
        )

        dialog.date_earliest_input.setText("2026-05-01")
        self.assertTrue(dialog.save_entry_button.isEnabled())
        self.assertEqual(
            dialog.preview_label.text(),
            "Preview: 1 May 2026, Fri",
        )

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

    def test_date_inputs_use_the_builtin_clear_button(self):
        dialog = self._dialog(self._movie_draft())
        dialog.show()

        for input_widget in (
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
        self.assertFalse(hasattr(dialog, "error_label"))
        self.assertEqual(
            dialog.preview_label.text(),
            "Preview: Invalid date — use YYYY-MM-DD",
        )
        self.assertFalse(dialog.save_entry_button.isEnabled())

        dialog.date_earliest_input.clear()
        dialog.copy_date_button.click()

        self.assertEqual(dialog.date_latest_input.text(), "")
        self.assertEqual(
            dialog.preview_label.text(),
            f"Preview: ~2020-{QDate.currentDate().year()}",
        )
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

    def test_season_label_mouse_toggle_selects_all_and_restores_watched_states(self):
        today = date.today()
        season_1_episode_1 = self._episode(11, 1, "Pilot", today)
        season_1_episode_2 = self._episode(12, 2, "Second", today)
        season_2_episode_1 = {
            **self._episode(21, 1, "Next season", today),
            "season_num": 2,
        }
        watched_row = {
            **deepcopy(season_1_episode_1),
            "watch_history_id": 90,
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
        }
        dialog = self._dialog(
            self._series_draft(
                [
                    season_1_episode_1,
                    season_1_episode_2,
                    season_2_episode_1,
                ],
                episode_watch_history=[watched_row],
            )
        )
        dialog.show()
        self.application.processEvents()

        season_1_label = self._season_label(dialog, 1)
        season_1_episode_1_button = dialog.episode_buttons[(1, 1)][0]
        season_1_episode_2_button = dialog.episode_buttons[(1, 2)][0]
        season_2_episode_1_button = dialog.episode_buttons[(2, 1)][0]

        season_label_right = season_1_label.mapTo(
            dialog,
            QPoint(season_1_label.width(), 0),
        ).x()
        first_episode_left = season_1_episode_1_button.mapTo(
            dialog,
            QPoint(0, 0),
        ).x()
        self.assertGreaterEqual(first_episode_left, season_label_right)

        self.assertEqual(
            season_1_episode_1_button.property("watchState"),
            "watched",
        )
        self.assertEqual(season_1_episode_2_button.property("watchState"), "")
        self.assertFalse(season_2_episode_1_button.isChecked())
        self.assertEqual(
            season_1_label.toolTip(),
            "Select all available episodes in Season 1.",
        )
        self.assertEqual(
            season_1_label.accessibleDescription(),
            season_1_label.toolTip(),
        )

        season_1_episode_1_button.click()
        self.assertTrue(season_1_episode_1_button.isChecked())
        self.assertFalse(season_1_episode_2_button.isChecked())

        QTest.mouseClick(
            season_1_label,
            Qt.MouseButton.LeftButton,
            pos=season_1_label.rect().center(),
        )

        self.assertTrue(season_1_episode_1_button.isChecked())
        self.assertTrue(season_1_episode_2_button.isChecked())
        self.assertFalse(season_2_episode_1_button.isChecked())
        self.assertEqual(
            season_1_episode_1_button.property("watchState"),
            "selected",
        )
        self.assertEqual(
            season_1_episode_2_button.property("watchState"),
            "selected",
        )
        self.assertEqual(
            season_1_label.toolTip(),
            "Clear all available episodes in Season 1.",
        )
        self.assertEqual(
            dialog.preview_label.text(),
            (
                f"Preview: ~2020-{QDate.currentDate().year()}"
                " · S1:E1-2"
            ),
        )

        QTest.mouseClick(
            season_1_label,
            Qt.MouseButton.LeftButton,
            pos=season_1_label.rect().center(),
        )

        self.assertFalse(season_1_episode_1_button.isChecked())
        self.assertFalse(season_1_episode_2_button.isChecked())
        self.assertFalse(season_2_episode_1_button.isChecked())
        self.assertEqual(
            season_1_episode_1_button.property("watchState"),
            "watched",
        )
        self.assertEqual(season_1_episode_2_button.property("watchState"), "")
        self.assertEqual(
            season_1_label.toolTip(),
            "Select all available episodes in Season 1.",
        )
        self.assertEqual(
            dialog.preview_label.text(),
            (
                f"Preview: ~2020-{QDate.currentDate().year()}"
                " · no episode info"
            ),
        )

    def test_season_label_keyboard_toggle_supports_enter_return_and_space(self):
        episodes = [
            self._episode(11, 1, "Pilot", date.today()),
            self._episode(12, 2, "Second", date.today()),
        ]

        for key in (
            Qt.Key.Key_Enter,
            Qt.Key.Key_Return,
            Qt.Key.Key_Space,
        ):
            with self.subTest(key=key):
                dialog = self._dialog(self._series_draft(episodes))
                dialog.show()
                self.application.processEvents()
                season_label = self._season_label(dialog, 1)
                season_label.setFocus()

                QTest.keyClick(season_label, key)

                self.assertTrue(dialog.episode_buttons[(1, 1)][0].isChecked())
                self.assertTrue(dialog.episode_buttons[(1, 2)][0].isChecked())

                QTest.keyClick(season_label, key)

                self.assertFalse(dialog.episode_buttons[(1, 1)][0].isChecked())
                self.assertFalse(dialog.episode_buttons[(1, 2)][0].isChecked())
                dialog.close()

    def test_season_toggle_changes_only_enabled_episodes_and_preserves_locked_selection(self):
        future = date.today() + timedelta(days=30)
        released = self._episode(11, 1, "Released", date.today())
        selected_unavailable = self._episode(13, 3, "Coming Soon", future)
        selected_row = {
            **deepcopy(selected_unavailable),
            "watch_history_id": 77,
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
        }
        media_draft = self._series_draft(
            [released, selected_unavailable],
            episode_watch_history=[selected_row],
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
        dialog.show()
        self.application.processEvents()

        season_label = self._season_label(dialog, 1)
        released_button = dialog.episode_buttons[(1, 1)][0]
        locked_button = dialog.episode_buttons[(1, 3)][0]

        self.assertFalse(dialog.save_entry_button.isEnabled())
        self.assertFalse(released_button.isChecked())
        self.assertTrue(locked_button.isChecked())
        self.assertFalse(locked_button.isEnabled())
        self.assertEqual(locked_button.property("watchState"), "selected")

        QTest.mouseClick(
            season_label,
            Qt.MouseButton.LeftButton,
            pos=season_label.rect().center(),
        )

        self.assertTrue(released_button.isChecked())
        self.assertTrue(locked_button.isChecked())
        self.assertTrue(dialog.save_entry_button.isEnabled())

        QTest.mouseClick(
            season_label,
            Qt.MouseButton.LeftButton,
            pos=season_label.rect().center(),
        )

        self.assertFalse(released_button.isChecked())
        self.assertTrue(locked_button.isChecked())
        self.assertFalse(dialog.save_entry_button.isEnabled())
        self.assertEqual(locked_button.property("watchState"), "selected")

        locked_only_dialog = self._dialog(
            self._series_draft(
                [selected_unavailable],
                episode_watch_history=[selected_row],
            ),
            entry,
        )
        locked_only_label = self._season_label(locked_only_dialog, 1)
        locked_only_button = locked_only_dialog.episode_buttons[(1, 3)][0]
        self.assertFalse(locked_only_label.isEnabled())
        self.assertTrue(locked_only_button.isChecked())
        self.assertFalse(locked_only_button.isEnabled())

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

    def test_enter_saves_valid_changes_instead_of_deleting_existing_entry(self):
        for key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            with self.subTest(key=key):
                entry = {
                    "kind": "media_event",
                    "watch_history_id": 50,
                    "date_earliest": "2026-05-01",
                    "date_latest": "2026-05-01",
                }
                dialog = self._dialog(self._movie_draft(), entry)
                dialog.show()
                dialog.date_latest_input.setText("2026-05-02")
                dialog.date_latest_input.setFocus()
                self.application.processEvents()

                self.assertTrue(dialog.save_entry_button.isDefault())
                self.assertTrue(dialog.save_entry_button.isEnabled())
                QTest.keyClick(dialog.date_latest_input, key)

                self.assertEqual(dialog.result(), QDialog.Accepted)
                self.assertEqual(dialog.result_payload["action"], "save")
                self.assertEqual(
                    dialog.result_payload["date_earliest"],
                    "2026-05-01",
                )
                self.assertEqual(
                    dialog.result_payload["date_latest"],
                    "2026-05-02",
                )

    def test_enter_cannot_delete_when_save_is_disabled(self):
        cases = (
            ("unchanged", "2026-05-01"),
            ("invalid", "not-a-date"),
        )

        for name, latest_date in cases:
            for key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                with self.subTest(case=name, key=key):
                    entry = {
                        "kind": "media_event",
                        "watch_history_id": 50,
                        "date_earliest": "2026-05-01",
                        "date_latest": "2026-05-01",
                    }
                    dialog = self._dialog(self._movie_draft(), entry)
                    dialog.show()
                    dialog.date_latest_input.setText(latest_date)
                    dialog.date_latest_input.setFocus()
                    self.application.processEvents()

                    self.assertFalse(dialog.save_entry_button.isEnabled())
                    QTest.keyClick(dialog.date_latest_input, key)
                    self.application.processEvents()

                    self.assertTrue(dialog.isVisible())
                    self.assertEqual(
                        dialog.result_payload,
                        {"action": "cancel"},
                    )
                    dialog.close()

    def test_explicit_save_and_delete_buttons_keep_their_actions(self):
        entry = {
            "kind": "media_event",
            "watch_history_id": 50,
            "date_earliest": "2026-05-01",
            "date_latest": "2026-05-01",
        }
        save_dialog = self._dialog(self._movie_draft(), entry)
        save_dialog.date_latest_input.setText("2026-05-02")

        save_dialog.save_entry_button.click()

        self.assertEqual(save_dialog.result(), QDialog.Accepted)
        self.assertEqual(save_dialog.result_payload["action"], "save")
        self.assertEqual(
            save_dialog.result_payload["date_latest"],
            "2026-05-02",
        )

        delete_dialog = self._dialog(self._movie_draft(), entry)

        delete_dialog.delete_entry_button.click()

        self.assertEqual(delete_dialog.result(), QDialog.Accepted)
        self.assertEqual(delete_dialog.result_payload, {"action": "delete"})

        keyboard_delete_dialog = self._dialog(self._movie_draft(), entry)
        keyboard_delete_dialog.show()
        keyboard_delete_dialog.delete_entry_button.setFocus()
        self.application.processEvents()

        QTest.keyClick(
            keyboard_delete_dialog.delete_entry_button,
            Qt.Key.Key_Return,
        )

        self.assertEqual(keyboard_delete_dialog.result(), QDialog.Accepted)
        self.assertEqual(
            keyboard_delete_dialog.result_payload,
            {"action": "delete"},
        )

    def _dialog(self, media_draft, entry=None):
        dialog = WatchEntryDetailsDialog(None, media_draft, entry)
        self.addCleanup(dialog.close)
        return dialog

    def _season_label(self, dialog, season_num):
        self.assertIn(season_num, dialog.season_labels)
        label = dialog.season_labels[season_num]
        self.assertEqual(label.text(), f"Season {season_num}:")
        return label

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
