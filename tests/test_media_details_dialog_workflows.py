import os
import sqlite3
import unittest
from copy import deepcopy
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QToolButton

from app.media_details.dialog import (
    REFRESH_FEEDBACK_DURATION_MS,
    MediaDetailsDialog,
    open_media_details_dialog,
)
from app.media_user_data.watch_history import get_series_episodes
from app.ui.top_bar import FIND_MEDIA_INPUT_PLACEHOLDER, INPUT_BOX_STYLE


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


class FakeWatchProviderRefreshManager(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    cancelled = Signal(str, object)
    finished = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.started = []
        self.cancelled_ids = []
        self._next_job_id = 0

    def start_refresh(self, media_id, match):
        self._next_job_id += 1
        job_id = f"providers-job-{self._next_job_id}"
        self.started.append((job_id, media_id, deepcopy(match)))
        return job_id

    def cancel(self, job_id):
        self.cancelled_ids.append(job_id)
        return True


class MediaDetailsDialogWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.manager = FakeRefreshManager()
        self.provider_manager = FakeWatchProviderRefreshManager()
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
        dialog.show()
        self.application.processEvents()
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
        self.assertEqual(
            dialog.metadata_refresh_status_label.text(),
            "Updated",
        )
        self.assertTrue(dialog.metadata_refresh_status_label.isVisible())
        self.assertTrue(dialog._metadata_refresh_feedback_timer.isActive())
        self.assertEqual(
            dialog._metadata_refresh_feedback_timer.interval(),
            REFRESH_FEEDBACK_DURATION_MS,
        )
        dialog._metadata_refresh_feedback_timer.timeout.emit()
        self.assertTrue(dialog.metadata_refresh_status_label.isHidden())
        self.assertEqual(dialog.metadata_refresh_status_label.text(), "")
        dialog.close()

    def test_metadata_progress_is_italic_and_rendered_in_the_header(self):
        dialog = self._dialog()
        dialog.show()
        self.application.processEvents()

        self.assertGreaterEqual(
            dialog.metadata_block.header_layout.indexOf(
                dialog.metadata_refresh_status_label
            ),
            0,
        )
        self.assertEqual(
            dialog.metadata_block.body_layout.indexOf(
                dialog.metadata_refresh_status_label
            ),
            -1,
        )
        self.assertTrue(
            dialog.metadata_refresh_status_label.font().italic()
        )

        dialog.reload_metadata()
        self.manager.progress.emit(
            "refresh-job",
            {"message": "Fetching series metadata"},
        )

        self.assertEqual(
            dialog.metadata_refresh_status_label.text(),
            "Fetching series metadata",
        )
        self.assertTrue(dialog.metadata_refresh_status_label.isVisible())
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
            "app.media_details.dialog.get_connection",
            return_value=conn,
        ), patch(
            "app.media_details.dialog.draft_saver.save_existing_media_changes",
            return_value=save_result,
        ) as local_save, patch(
            "app.media_details.dialog.draft_saver.save_media_draft_with_posters",
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

    def test_find_media_input_uses_the_builtin_clear_button(self):
        dialog = self._dialog()
        dialog.show()

        input_widget = dialog.find_media_input
        self.assertTrue(input_widget.isClearButtonEnabled())
        input_widget.setText("clear me")
        self.application.processEvents()
        clear_button = input_widget.findChild(QToolButton)

        self.assertIsNotNone(clear_button)
        self.assertTrue(clear_button.isVisible())
        clear_button.click()
        self.assertEqual(input_widget.text(), "")

        dialog.close()

    def test_find_media_uses_label_placeholder_and_main_input_style(self):
        dialog = self._dialog()

        self.assertEqual(dialog.find_media_label.text(), "Find Media:")
        self.assertEqual(
            dialog.find_media_input.placeholderText(),
            FIND_MEDIA_INPUT_PLACEHOLDER,
        )
        self.assertEqual(
            dialog.find_media_input.styleSheet(),
            INPUT_BOX_STYLE,
        )

        self.assertFalse(hasattr(dialog, "find_media_button"))
        dialog.close()

    def test_find_media_is_submitted_with_enter(self):
        dialog = self._dialog()
        dialog.find_media_input.setText("tt1234567")

        with patch(
            "app.media_details.dialog.resolve_media_draft_from_query",
            return_value=None,
        ) as resolve_media:
            QTest.keyClick(dialog.find_media_input, Qt.Key.Key_Return)

        resolve_media.assert_called_once_with(dialog, "tt1234567")
        dialog.close()

    def test_smart_fill_controls_are_not_loaded(self):
        dialog = self._dialog()

        self.assertFalse(hasattr(dialog, "smart_label"))
        self.assertFalse(hasattr(dialog, "smart_input"))
        dialog.close()

    def test_initial_watched_status_does_not_open_watch_entry_details(self):
        with patch(
            "app.media_details.dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            dialog = self._dialog(watch_state="watched")
            self.application.processEvents()

        watch_entry_dialog.assert_not_called()
        dialog.close()

    def test_user_transition_to_watched_opens_one_new_entry_for_each_media_type(self):
        for media_type in ("movie", "series", "episode"):
            with self.subTest(media_type=media_type), patch(
                "app.media_details.dialog.WatchEntryDetailsDialog",
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
                    "app.media_details.dialog.WatchEntryDetailsDialog",
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
                "app.media_details.dialog.WatchEntryDetailsDialog",
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
            "app.media_details.dialog.WatchEntryDetailsDialog",
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
                "app.media_details.dialog.WatchEntryDetailsDialog",
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
            "app.media_details.dialog.WatchEntryDetailsDialog",
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
            "app.media_details.dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            dialog = self._dialog()

            watched_index = dialog.status_combo.findData("watched")
            dialog.status_combo.setCurrentIndex(watched_index)
            self.application.processEvents()

        watch_entry_dialog.assert_not_called()
        dialog.close()

    def test_user_transition_to_other_status_does_not_open_watch_entry_details(self):
        with patch(
            "app.media_details.dialog.WatchEntryDetailsDialog",
        ) as watch_entry_dialog:
            dialog = self._dialog()

            self._activate_status(dialog, "not_interested")

        watch_entry_dialog.assert_not_called()
        dialog.close()

    def test_scheduled_entry_is_ignored_after_dialog_accepts(self):
        with patch(
            "app.media_details.dialog.WatchEntryDetailsDialog",
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

    def test_existing_media_starts_automatic_provider_refresh_after_show(self):
        dialog = self._dialog(auto_refresh_watch_providers=True)

        self.assertEqual(self.provider_manager.started, [])
        dialog.show()
        self.application.processEvents()

        self.assertEqual(len(self.provider_manager.started), 1)
        _job_id, media_id, match = self.provider_manager.started[0]
        self.assertEqual(media_id, 1)
        self.assertEqual(
            match,
            {"media_type": "series", "tmdb_id": 100},
        )
        self.assertEqual(self.manager.started, [])
        self.assertFalse(dialog.providers_block.action_button.isEnabled())
        self.assertTrue(dialog.metadata_block.action_button.isEnabled())
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.isHidden()
        )
        dialog.close()

    def test_new_media_does_not_start_automatic_provider_refresh(self):
        dialog = self._dialog(
            media_id=None,
            auto_refresh_watch_providers=True,
        )
        dialog.show()
        self.application.processEvents()

        self.assertEqual(self.provider_manager.started, [])
        dialog.close()

    def test_automatic_provider_success_persists_and_updates_both_drafts(self):
        old_providers = [self._provider(1, "Old Service")]
        new_providers = [self._provider(8, "Netflix")]
        dialog = self._dialog(
            providers=old_providers,
            auto_refresh_watch_providers=True,
        )
        dialog.show()
        self.application.processEvents()
        job_id = self.provider_manager.started[0][0]
        good_index = dialog.impression_combo.findData("good")
        dialog.impression_combo.setCurrentIndex(good_index)
        self.assertTrue(dialog._is_dirty)
        conn = sqlite3.connect(":memory:")

        with patch(
            "app.media_details.dialog.get_connection",
            return_value=conn,
        ), patch(
            "app.media_details.dialog.media_repo.replace_media_watch_providers",
        ) as replace_providers:
            self.provider_manager.succeeded.emit(
                job_id,
                {
                    "media_id": 1,
                    "watch_providers": new_providers,
                    "checked_at": "2026-08-14 12:00:00",
                },
            )

        replace_providers.assert_called_once_with(
            conn,
            1,
            new_providers,
            checked_at="2026-08-14 12:00:00",
        )
        self.assertEqual(dialog.media_draft["watch_providers"], new_providers)
        self.assertEqual(
            dialog._baseline_media_draft["watch_providers"],
            new_providers,
        )

        for draft in (dialog.media_draft, dialog._baseline_media_draft):
            self.assertEqual(
                draft["metadata"]["last_tmdb_watch_providers_checked_at"],
                "2026-08-14 12:00:00",
            )

        self.assertTrue(dialog._is_dirty)
        self.assertEqual(dialog.impression_combo.currentData(), "good")
        self.assertTrue(dialog.result_payload["database_changed"])
        self.provider_manager.finished.emit(job_id, {"status": "succeeded"})
        self.assertTrue(dialog.providers_block.action_button.isEnabled())
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.isHidden()
        )
        self.assertFalse(
            dialog._watch_provider_refresh_feedback_timer.isActive()
        )
        conn.close()
        dialog.close()

    def test_automatic_empty_provider_result_clears_existing_providers(self):
        dialog = self._dialog(
            providers=[self._provider(1, "Old Service")],
            auto_refresh_watch_providers=True,
        )
        dialog.show()
        self.application.processEvents()
        job_id = self.provider_manager.started[0][0]
        conn = sqlite3.connect(":memory:")

        with patch(
            "app.media_details.dialog.get_connection",
            return_value=conn,
        ), patch(
            "app.media_details.dialog.media_repo.replace_media_watch_providers",
        ) as replace_providers:
            self.provider_manager.succeeded.emit(
                job_id,
                {
                    "media_id": 1,
                    "watch_providers": [],
                    "checked_at": "2026-08-14 12:00:00",
                },
            )

        replace_providers.assert_called_once_with(
            conn,
            1,
            [],
            checked_at="2026-08-14 12:00:00",
        )
        self.assertEqual(dialog.media_draft["watch_providers"], [])
        self.assertEqual(dialog._baseline_media_draft["watch_providers"], [])
        conn.close()
        dialog.close()

    def test_automatic_provider_failures_are_silent_and_preserve_drafts(self):
        old_providers = [self._provider(1, "Old Service")]
        dialog = self._dialog(
            providers=old_providers,
            auto_refresh_watch_providers=True,
        )
        dialog.show()
        self.application.processEvents()
        job_id = self.provider_manager.started[0][0]

        with patch("app.media_details.dialog.QMessageBox.warning") as warning:
            self.provider_manager.failed.emit(
                job_id,
                {"message": "offline", "type": "ConnectionError"},
            )
            self.provider_manager.finished.emit(
                job_id,
                {"status": "failed"},
            )

        warning.assert_not_called()
        self.assertEqual(dialog.media_draft["watch_providers"], old_providers)
        self.assertEqual(
            dialog._baseline_media_draft["watch_providers"],
            old_providers,
        )
        self.assertNotIn("database_changed", dialog.result_payload)
        self.assertTrue(dialog.providers_block.action_button.isEnabled())
        dialog.close()

    def test_automatic_provider_database_failure_is_silent_and_atomic(self):
        old_providers = [self._provider(1, "Old Service")]
        dialog = self._dialog(
            providers=old_providers,
            auto_refresh_watch_providers=True,
        )
        dialog.show()
        self.application.processEvents()
        job_id = self.provider_manager.started[0][0]
        conn = sqlite3.connect(":memory:")

        with patch(
            "app.media_details.dialog.get_connection",
            return_value=conn,
        ), patch(
            "app.media_details.dialog.media_repo.replace_media_watch_providers",
            side_effect=RuntimeError("database unavailable"),
        ), patch("app.media_details.dialog.QMessageBox.warning") as warning:
            self.provider_manager.succeeded.emit(
                job_id,
                {
                    "media_id": 1,
                    "watch_providers": [self._provider(8, "Netflix")],
                    "checked_at": "2026-08-14 12:00:00",
                },
            )

        warning.assert_not_called()
        self.assertEqual(dialog.media_draft["watch_providers"], old_providers)
        self.assertEqual(
            dialog._baseline_media_draft["watch_providers"],
            old_providers,
        )
        self.assertNotIn("database_changed", dialog.result_payload)
        conn.close()
        dialog.close()

    def test_closing_cancels_provider_refresh_and_ignores_late_success(self):
        dialog = self._dialog(auto_refresh_watch_providers=True)
        dialog.show()
        self.application.processEvents()
        job_id = self.provider_manager.started[0][0]

        dialog.reject()

        self.assertIn(job_id, self.provider_manager.cancelled_ids)

        with patch("app.media_details.dialog.get_connection") as get_connection:
            self.provider_manager.succeeded.emit(
                job_id,
                {
                    "media_id": 1,
                    "watch_providers": [self._provider(8, "Netflix")],
                    "checked_at": "2026-08-14 12:00:00",
                },
            )

        get_connection.assert_not_called()
        self.assertEqual(dialog.media_draft["watch_providers"], [])

    def test_replacing_draft_ignores_stale_provider_result(self):
        dialog = self._dialog(auto_refresh_watch_providers=True)
        dialog.show()
        self.application.processEvents()
        stale_job_id = self.provider_manager.started[0][0]
        replacement = self._series_draft()
        replacement["media_id"] = 2

        dialog.set_media_draft(replacement)
        self.application.processEvents()

        self.assertIn(stale_job_id, self.provider_manager.cancelled_ids)
        self.assertEqual(self.provider_manager.started[-1][1], 2)

        with patch("app.media_details.dialog.get_connection") as get_connection:
            self.provider_manager.succeeded.emit(
                stale_job_id,
                {
                    "media_id": 1,
                    "watch_providers": [self._provider(8, "Netflix")],
                    "checked_at": "2026-08-14 12:00:00",
                },
            )

        get_connection.assert_not_called()
        self.assertEqual(dialog.media_draft["media_id"], 2)
        self.assertEqual(dialog.media_draft["watch_providers"], [])
        dialog.close()

    def test_replacing_same_draft_restarts_cancelled_provider_refresh(self):
        dialog = self._dialog(auto_refresh_watch_providers=True)
        dialog.show()
        self.application.processEvents()
        first_job_id = self.provider_manager.started[0][0]

        dialog.set_media_draft(self._series_draft())
        self.application.processEvents()

        self.assertIn(first_job_id, self.provider_manager.cancelled_ids)
        self.assertEqual(len(self.provider_manager.started), 2)
        second_job_id, media_id, _match = self.provider_manager.started[-1]
        self.assertNotEqual(second_job_id, first_job_id)
        self.assertEqual(media_id, 1)
        dialog.close()

    def test_manual_provider_success_shows_transient_header_feedback(self):
        providers = [self._provider(8, "Netflix")]
        dialog = self._dialog()
        dialog.show()
        self.application.processEvents()

        dialog.reload_watch_providers()
        job_id = self.provider_manager.started[-1][0]

        self.assertGreaterEqual(
            dialog.providers_block.header_layout.indexOf(
                dialog.watch_provider_refresh_status_label
            ),
            0,
        )
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.font().italic()
        )
        self.assertEqual(
            dialog.watch_provider_refresh_status_label.text(),
            "Fetching providers…",
        )
        self.assertFalse(
            dialog.providers_block.action_button.isEnabled()
        )
        conn = sqlite3.connect(":memory:")

        with patch(
            "app.media_details.dialog.get_connection",
            return_value=conn,
        ), patch(
            "app.media_details.dialog.media_repo.replace_media_watch_providers",
        ) as replace_providers:
            self.provider_manager.succeeded.emit(
                job_id,
                {
                    "media_id": 1,
                    "watch_providers": providers,
                    "checked_at": "2026-08-15 12:00:00",
                },
            )

        self.provider_manager.finished.emit(
            job_id,
            {"status": "succeeded"},
        )

        replace_providers.assert_called_once_with(
            conn,
            1,
            providers,
            checked_at="2026-08-15 12:00:00",
        )
        self.assertEqual(
            dialog.watch_provider_refresh_status_label.text(),
            "Updated",
        )
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.isVisible()
        )
        self.assertTrue(
            dialog._watch_provider_refresh_feedback_timer.isActive()
        )
        self.assertEqual(
            dialog._watch_provider_refresh_feedback_timer.interval(),
            REFRESH_FEEDBACK_DURATION_MS,
        )
        self.assertTrue(dialog.providers_block.action_button.isEnabled())
        self.assertTrue(dialog.result_payload["database_changed"])

        dialog._watch_provider_refresh_feedback_timer.timeout.emit()
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.isHidden()
        )
        self.assertEqual(
            dialog.watch_provider_refresh_status_label.text(),
            "",
        )
        conn.close()
        dialog.close()

    def test_manual_provider_success_updates_unsaved_media_without_database(self):
        providers = [self._provider(8, "Netflix")]
        dialog = self._dialog(media_id=None)
        dialog.show()
        self.application.processEvents()

        dialog.reload_watch_providers()
        job_id, media_id, _match = self.provider_manager.started[-1]
        self.assertIsNone(media_id)

        with patch("app.media_details.dialog.get_connection") as get_connection:
            self.provider_manager.succeeded.emit(
                job_id,
                {
                    "media_id": None,
                    "watch_providers": providers,
                    "checked_at": "2026-08-15 12:00:00",
                },
            )

        self.provider_manager.finished.emit(
            job_id,
            {"status": "succeeded"},
        )

        get_connection.assert_not_called()
        self.assertEqual(dialog.media_draft["watch_providers"], providers)
        self.assertEqual(
            dialog.media_draft["metadata"][
                "last_tmdb_watch_providers_checked_at"
            ],
            "2026-08-15 12:00:00",
        )
        self.assertTrue(dialog._is_dirty)
        self.assertEqual(
            dialog.watch_provider_refresh_status_label.text(),
            "Updated",
        )
        self.assertNotIn("database_changed", dialog.result_payload)
        dialog.close()

    def test_manual_provider_refresh_still_reports_network_failure(self):
        dialog = self._dialog()
        dialog.show()
        self.application.processEvents()
        dialog.reload_watch_providers()
        job_id = self.provider_manager.started[-1][0]

        self.assertEqual(
            dialog.watch_provider_refresh_status_label.text(),
            "Fetching providers…",
        )
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.isVisible()
        )

        with patch("app.media_details.dialog.QMessageBox.warning") as warning:
            self.provider_manager.failed.emit(
                job_id,
                {"message": "offline", "type": "ConnectionError"},
            )
            self.provider_manager.finished.emit(
                job_id,
                {"status": "failed"},
            )

        warning.assert_called_once_with(
            dialog,
            "Watch Providers",
            "offline",
        )
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.isHidden()
        )
        dialog.close()

    def test_manual_provider_database_failure_preserves_live_draft(self):
        old_providers = [self._provider(1, "Old Service")]
        dialog = self._dialog(providers=old_providers)
        dialog.show()
        self.application.processEvents()
        dialog.reload_watch_providers()
        job_id = self.provider_manager.started[-1][0]
        conn = sqlite3.connect(":memory:")

        with patch(
            "app.media_details.dialog.get_connection",
            return_value=conn,
        ), patch(
            "app.media_details.dialog.media_repo.replace_media_watch_providers",
            side_effect=RuntimeError("database unavailable"),
        ), patch("app.media_details.dialog.QMessageBox.warning") as warning:
            self.provider_manager.succeeded.emit(
                job_id,
                {
                    "media_id": 1,
                    "watch_providers": [self._provider(8, "Netflix")],
                    "checked_at": "2026-08-14 12:00:00",
                },
            )
            self.provider_manager.finished.emit(
                job_id,
                {"status": "succeeded"},
            )

        warning.assert_called_once_with(
            dialog,
            "Watch Providers",
            "database unavailable",
        )
        self.assertEqual(dialog.media_draft["watch_providers"], old_providers)
        self.assertEqual(
            dialog._baseline_media_draft["watch_providers"],
            old_providers,
        )
        self.assertNotIn("database_changed", dialog.result_payload)
        self.assertTrue(
            dialog.watch_provider_refresh_status_label.isHidden()
        )
        conn.close()
        dialog.close()

    def test_rejected_wrapper_preserves_database_change_result(self):
        with patch(
            "app.media_details.dialog.MediaDetailsDialog"
        ) as dialog_class:
            dialog = dialog_class.return_value
            dialog.exec.return_value = QDialog.Rejected
            dialog.result_payload = {
                "status": "cancelled",
                "database_changed": True,
            }

            result = open_media_details_dialog(None, {"media_id": 1})

        self.assertEqual(
            result,
            {"status": "cancelled", "database_changed": True},
        )

    def _dialog(
        self,
        media_type="series",
        watch_state="to_watch",
        watch_history=None,
        media_id=1,
        providers=None,
        auto_refresh_watch_providers=False,
    ):
        media_draft = self._series_draft(
            media_type=media_type,
            watch_state=watch_state,
        )
        media_draft["user_data"]["watch_history"] = list(
            watch_history or []
        )
        media_draft["media_id"] = media_id
        media_draft["watch_providers"] = deepcopy(providers or [])
        return MediaDetailsDialog(
            None,
            media_draft,
            metadata_refresh_manager=self.manager,
            watch_provider_refresh_manager=self.provider_manager,
            auto_refresh_watch_providers=auto_refresh_watch_providers,
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

    def _provider(self, provider_tmdb_id, provider_name):
        return {
            "provider_tmdb_id": provider_tmdb_id,
            "provider_name": provider_name,
            "country_code": "AT",
            "access_type": "flatrate",
        }


if __name__ == "__main__":
    unittest.main()
