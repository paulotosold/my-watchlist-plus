import os
import sqlite3
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QToolButton

from app.media_details_dialog import MediaDetailsDialog
from app.top_bar import FIND_MEDIA_INPUT_PLACEHOLDER, INPUT_BOX_STYLE
from app.watch_history_editor import get_series_episodes


class FakeRefreshManager(QObject):
    progress = Signal(str, object)
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    cancelled = Signal(str, object)
    finished = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.started = []
        self.cancelled_ids = []

    def start_refresh(self, media_id, match):
        self.started.append((media_id, match))
        return "refresh-job"

    def cancel(self, job_id):
        self.cancelled_ids.append(job_id)
        return True


class MediaDetailsDialogWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.manager = FakeRefreshManager()
        self.load_lists_patch = patch.object(
            MediaDetailsDialog,
            "_load_all_lists",
            lambda dialog: setattr(dialog, "all_lists", []),
        )
        self.load_lists_patch.start()

    def tearDown(self):
        self.load_lists_patch.stop()
        self.application.processEvents()

    def test_reload_merges_catalog_and_preserves_pending_user_edit(self):
        dialog = self._dialog()
        dialog.impression_combo.setCurrentIndex(
            dialog.impression_combo.findData("good")
        )

        dialog.reload_metadata()

        self.assertFalse(dialog.save_button.isEnabled())
        self.assertEqual(self.manager.started[0][0], 1)
        self.manager.succeeded.emit(
            "refresh-job",
            {
                "snapshot": {"media_type": "series", "tmdb_id": 100},
                "refresh_result": {
                    "metadata": {
                        "tmdb_id": 100,
                        "media_type": "series",
                        "title": "Updated Series",
                        "last_tmdb_metadata_checked_at": "2026-07-13 12:00:00",
                    },
                    "series_catalog": {
                        "summary": {"season_count": 1, "episode_count": 2},
                        "episodes": [
                            self._episode(11, 101, 1),
                            self._episode(12, 102, 2),
                        ],
                    },
                    "stats": {
                        "created": 0,
                        "updated": 1,
                        "preserved_missing": 0,
                    },
                },
            },
        )
        self.manager.finished.emit(
            "refresh-job",
            {"status": "succeeded", "payload": {}},
        )

        self.assertEqual(dialog.media_draft["user_data"]["impression"], "good")
        self.assertIsNone(
            dialog._baseline_media_draft["user_data"]["impression"]
        )
        self.assertEqual(len(get_series_episodes(dialog.media_draft)), 2)
        self.assertEqual(
            dialog.media_draft["metadata"]["title"],
            "Updated Series",
        )
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertFalse(dialog._metadata_refresh_in_progress)
        dialog.close()

    def test_existing_save_uses_local_incremental_path(self):
        dialog = self._dialog()
        dialog.impression_combo.setCurrentIndex(
            dialog.impression_combo.findData("very_good")
        )
        conn = sqlite3.connect(":memory:")
        save_result = {
            "media_id": 1,
            "poster_downloads": {"downloaded": [], "skipped": [], "failed": []},
            "saved_media_type": "series",
            "saved_title": "Series",
            "inserted_ids_by_draft_id": {
                "media_watch_history": {},
                "series_episode_watch_history": {},
                "notes": {},
            },
            "counts": {},
        }

        with patch(
            "app.media_details_dialog.get_connection",
            return_value=conn,
        ), patch(
            "app.media_details_dialog.draft_saver.save_existing_media_changes",
            return_value=save_result,
        ) as local_save, patch(
            "app.media_details_dialog.draft_saver.save_media_draft_with_posters",
        ) as import_save:
            dialog.save_media()

        local_save.assert_called_once()
        baseline = local_save.call_args.args[1]
        current = local_save.call_args.args[2]
        self.assertIsNone(baseline["user_data"]["impression"])
        self.assertEqual(current["user_data"]["impression"], "very_good")
        import_save.assert_not_called()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        conn.close()

    def test_closing_during_reload_requests_cancellation(self):
        dialog = self._dialog()
        dialog.reload_metadata()

        dialog.reject()

        self.assertEqual(self.manager.cancelled_ids, ["refresh-job"])

    def test_find_media_and_smart_inputs_use_the_builtin_clear_button(self):
        dialog = self._dialog()
        dialog.show()

        for input_widget in (
            dialog.find_media_input,
            dialog.smart_input,
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

        dialog.close()

    def test_find_media_and_smart_fill_use_labels_and_main_input_style(self):
        dialog = self._dialog()

        self.assertEqual(dialog.find_media_label.text(), "Find Media:")
        self.assertEqual(dialog.smart_label.text(), "Smart Fill:")
        self.assertEqual(
            dialog.find_media_input.placeholderText(),
            FIND_MEDIA_INPUT_PLACEHOLDER,
        )

        for input_widget in (dialog.find_media_input, dialog.smart_input):
            with self.subTest(input_widget=input_widget):
                self.assertEqual(input_widget.styleSheet(), INPUT_BOX_STYLE)

        self.assertFalse(hasattr(dialog, "find_media_button"))
        self.assertFalse(hasattr(dialog, "smart_button"))
        dialog.close()

    def test_find_media_and_smart_fill_are_submitted_with_enter(self):
        dialog = self._dialog()
        dialog.find_media_input.setText("tt1234567")
        dialog.smart_input.setText("watched yesterday")

        with patch(
            "app.media_details_dialog.resolve_media_draft_from_query",
            return_value=None,
        ) as resolve_media:
            QTest.keyClick(dialog.find_media_input, Qt.Key.Key_Return)

        with patch("builtins.print") as print_mock:
            QTest.keyClick(dialog.smart_input, Qt.Key.Key_Return)

        resolve_media.assert_called_once_with(dialog, "tt1234567")
        print_mock.assert_called_once_with("Smart Fill clicked")
        dialog.close()

    def test_initial_watched_status_does_not_open_watch_entry_details(self):
        with patch(
            "app.media_details_dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            dialog = self._dialog(watch_state="watched")
            self.application.processEvents()

        watch_entry_dialog.assert_not_called()
        dialog.close()

    def test_user_transition_to_watched_opens_one_new_entry_for_each_media_type(self):
        for media_type in ("movie", "series", "episode"):
            with self.subTest(media_type=media_type), patch(
                "app.media_details_dialog.WatchEntryDetailsDialog",
            ) as watch_entry_dialog:
                watch_entry_dialog.return_value.exec.return_value = QDialog.Rejected
                dialog = self._dialog(media_type=media_type)

                self._activate_status(dialog, "watched")

                watch_entry_dialog.assert_called_once()
                call = watch_entry_dialog.call_args
                entry = (
                    call.args[2]
                    if len(call.args) > 2
                    else call.kwargs.get("entry")
                )
                self.assertIsNone(entry)
                dialog.close()

    def test_cancelling_automatic_entry_restores_movie_and_episode_status(self):
        for media_type in ("movie", "episode"):
            for previous_status in (None, "to_watch"):
                with self.subTest(
                    media_type=media_type,
                    previous_status=previous_status,
                ), patch(
                    "app.media_details_dialog.WatchEntryDetailsDialog",
                ) as watch_entry_dialog:
                    watch_entry_dialog.return_value.exec.return_value = (
                        QDialog.Rejected
                    )
                    dialog = self._dialog(
                        media_type=media_type,
                        watch_state=previous_status,
                    )

                    self._activate_status(dialog, "watched")
                    dialog._apply_form_to_draft()

                    self.assertEqual(
                        dialog.status_combo.currentData(),
                        previous_status,
                    )
                    self.assertEqual(
                        dialog.media_draft["user_data"]["watch_state"],
                        previous_status,
                    )
                    self.assertEqual(
                        dialog.media_draft["user_data"]["watch_history"],
                        [],
                    )
                    self.assertFalse(dialog._is_dirty)
                    self.assertFalse(dialog.save_button.isEnabled())
                    dialog.close()

    def test_cancelling_automatic_entry_preserves_prior_dirty_state(self):
        for media_type in ("movie", "episode"):
            with self.subTest(media_type=media_type), patch(
                "app.media_details_dialog.WatchEntryDetailsDialog",
            ) as watch_entry_dialog:
                watch_entry_dialog.return_value.exec.return_value = (
                    QDialog.Rejected
                )
                dialog = self._dialog(
                    media_type=media_type,
                    watch_state="to_watch",
                )
                good_index = dialog.impression_combo.findData("good")
                self.assertGreaterEqual(good_index, 0)
                dialog.impression_combo.setCurrentIndex(good_index)
                self.assertTrue(dialog._is_dirty)
                self.assertTrue(dialog.save_button.isEnabled())

                self._activate_status(dialog, "watched")

                self.assertEqual(
                    dialog.status_combo.currentData(),
                    "to_watch",
                )
                self.assertEqual(
                    dialog.impression_combo.currentData(),
                    "good",
                )
                self.assertTrue(dialog._is_dirty)
                self.assertTrue(dialog.save_button.isEnabled())
                dialog.close()

    def test_cancelling_manual_entry_does_not_change_watched_status(self):
        with patch(
            "app.media_details_dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            watch_entry_dialog.return_value.exec.return_value = QDialog.Rejected
            dialog = self._dialog(media_type="movie", watch_state="watched")

            dialog.add_watch_history()

        self.assertEqual(dialog.status_combo.currentData(), "watched")
        dialog.close()

    def test_cancelling_automatic_entry_keeps_watched_with_existing_history(self):
        existing_history = [{
            "id": 20,
            "date_earliest": "2026-01-01",
            "date_latest": "2026-01-01",
        }]

        for media_type in ("movie", "episode"):
            with self.subTest(media_type=media_type), patch(
                "app.media_details_dialog.WatchEntryDetailsDialog",
            ) as watch_entry_dialog:
                watch_entry_dialog.return_value.exec.return_value = (
                    QDialog.Rejected
                )
                dialog = self._dialog(
                    media_type=media_type,
                    watch_history=existing_history,
                )

                self._activate_status(dialog, "watched")

                self.assertEqual(
                    dialog.status_combo.currentData(),
                    "watched",
                )
                self.assertEqual(
                    dialog.media_draft["user_data"]["watch_history"],
                    existing_history,
                )
                self.assertTrue(dialog._is_dirty)
                self.assertTrue(dialog.save_button.isEnabled())
                dialog.close()

    def test_cancelling_automatic_entry_keeps_watched_status_for_series(self):
        with patch(
            "app.media_details_dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            watch_entry_dialog.return_value.exec.return_value = QDialog.Rejected
            dialog = self._dialog()

            self._activate_status(dialog, "watched")

        self.assertEqual(dialog.status_combo.currentData(), "watched")
        self.assertTrue(dialog._is_dirty)
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.close()

    def test_programmatic_watched_status_does_not_open_or_recurse(self):
        with patch(
            "app.media_details_dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            dialog = self._dialog()

            watched_index = dialog.status_combo.findData("watched")
            dialog.status_combo.setCurrentIndex(watched_index)
            self.application.processEvents()

        watch_entry_dialog.assert_not_called()
        dialog.close()

    def test_user_transition_to_other_status_does_not_open_watch_entry_details(self):
        with patch(
            "app.media_details_dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            dialog = self._dialog()

            self._activate_status(dialog, "not_interested")

        watch_entry_dialog.assert_not_called()
        dialog.close()

    def test_scheduled_entry_is_ignored_after_dialog_accepts(self):
        with patch(
            "app.media_details_dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            dialog = self._dialog()
            watched_index = dialog.status_combo.findData("watched")
            dialog.status_combo.setCurrentIndex(watched_index)
            dialog.status_combo.activated.emit(watched_index)
            dialog.accept()
            self.application.processEvents()

        watch_entry_dialog.assert_not_called()

    def test_long_watch_providers_scroll_without_resizing_columns(self):
        dialog = self._dialog()
        dialog.show()
        self.application.processEvents()
        initial_widths = (
            dialog.metadata_block.width(),
            dialog.providers_block.width(),
        )
        dialog.media_draft["watch_providers"] = [
            {
                "provider_name": (
                    f"Very Long Provider Name {index} with Additional Channel Text"
                ),
                "access_type": "flatrate",
            }
            for index in range(20)
        ]

        dialog.render_watch_providers()
        self.application.processEvents()

        self.assertEqual(
            (
                dialog.metadata_block.width(),
                dialog.providers_block.width(),
            ),
            initial_widths,
        )
        self.assertGreater(
            dialog.providers_scroll.horizontalScrollBar().maximum(),
            0,
        )
        self.assertEqual(
            dialog.providers_scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        dialog.close()

    def _dialog(
        self,
        media_type="series",
        watch_state="to_watch",
        watch_history=None,
    ):
        media_draft = self._series_draft(
            media_type=media_type,
            watch_state=watch_state,
        )
        media_draft["user_data"]["watch_history"] = list(
            watch_history or []
        )
        return MediaDetailsDialog(
            None,
            media_draft,
            metadata_refresh_manager=self.manager,
        )

    def _activate_status(self, dialog, watch_state):
        index = dialog.status_combo.findData(watch_state)
        self.assertGreaterEqual(index, 0)
        dialog.status_combo.setCurrentIndex(index)
        dialog.status_combo.activated.emit(index)
        self.application.processEvents()

    def _series_draft(self, media_type="series", watch_state="to_watch"):
        return {
            "media_id": 1,
            "metadata": {
                "tmdb_id": 100,
                "imdb_id": "tt100",
                "media_type": media_type,
                "title": "Series",
                "original_title": "Series",
                "production_status": "Returning Series",
                "release_date": "2026-01-01",
                "runtime_min": None,
                "genres": [],
                "spoken_languages": [],
                "origin_language": None,
                "production_countries": [],
                "production_companies": [],
                "directors": [],
                "creators": [],
                "writers": [],
                "actors": [],
            },
            "series_view": {
                "summary": {"season_count": 1, "episode_count": 1},
                "episodes": [self._episode(11, 101, 1)],
                "episode_watch_history": [],
            },
            "watch_providers": [],
            "posters": [],
            "user_data": {
                "watch_state": watch_state,
                "impression": None,
                "is_collection_pick": None,
                "watch_history": [],
                "notes": [],
                "lists": [],
            },
        }

    def _episode(self, episode_id, tmdb_id, episode_num):
        return {
            "series_id": 1,
            "episode_id": episode_id,
            "tmdb_id": tmdb_id,
            "season_num": 1,
            "episode_num": episode_num,
            "title": f"Episode {episode_num}",
            "release_date": "2026-01-01",
        }


if __name__ == "__main__":
    unittest.main()
