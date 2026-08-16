import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

import app.media_repository as media_repository
import app.media_draft.builder as draft_builder
import app.media_draft.saver as draft_saver
from app.media_details.poster_dialog import (
    LARGE_POSTER_PREVIEW_SIZE,
    MANAGE_POSTER_HEIGHT,
    MANAGE_POSTER_PREVIEW_SIZE,
    MANAGE_POSTER_WIDTH,
    MANAGE_POSTERS_COLUMNS,
    MANAGE_POSTERS_HEIGHT,
    MANAGE_POSTERS_WIDTH,
    ManagePostersDialog,
    PosterPreviewDialog,
)
from db.connection import SCHEMA_PATH


class FakeDiscoveryManager(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, object)
    finished = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.started = []
        self.cancelled = []

    def start(self, match):
        self.started.append(deepcopy(match))
        return f"job-{len(self.started)}"

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        return True


class FakePreviewLoader(QObject):
    poster_loaded = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.requested = []

    def request(self, filename):
        url = f"preview:{filename}"
        self.requested.append(filename)
        return url


class ManagePostersDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.manager = FakeDiscoveryManager()
        self.preview_loader = FakePreviewLoader()

    def tearDown(self):
        self.application.processEvents()

    def test_fixed_geometry_grid_and_database_order(self):
        draft = self._draft([
            self._poster("b.jpg"),
            self._poster("default.jpg", is_default=True),
            self._poster("a.jpg"),
            self._poster("c.jpg"),
        ])
        dialog = self._dialog(draft)
        dialog.show()
        self.application.processEvents()

        self.assertEqual(dialog.width(), MANAGE_POSTERS_WIDTH)
        self.assertEqual(dialog.height(), MANAGE_POSTERS_HEIGHT)
        self.assertEqual(MANAGE_POSTERS_COLUMNS, 5)
        self.assertEqual((MANAGE_POSTER_WIDTH, MANAGE_POSTER_HEIGHT), (185, 278))
        self.assertEqual(MANAGE_POSTER_PREVIEW_SIZE, "w342")
        self.assertEqual(
            [poster["filename"] for poster in dialog._ordered_candidates()],
            ["default.jpg", "b.jpg", "a.jpg", "c.jpg"],
        )
        self.assertEqual(
            dialog.scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            dialog.scroll.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            dialog.scroll.viewport().objectName(),
            "managePostersViewport",
        )
        self.assertNotIn("> QWidget", dialog.styleSheet())
        first_left = dialog.import_container.geometry().left()
        last_right = dialog.cards["poster:c.jpg"].geometry().right()
        right_margin = dialog.content.width() - last_right - 1
        self.assertLessEqual(abs(first_left - right_margin), 1)
        default_card = dialog.cards["poster:default.jpg"]
        card_gap = default_card.geometry().left() - dialog.import_container.geometry().right() - 1
        self.assertEqual(card_gap, 20)
        self.assertLess(
            default_card.keep_checkbox.geometry().right(),
            default_card.default_radio.geometry().left(),
        )
        default_right_margin = (
            default_card.width() - default_card.default_radio.geometry().right() - 1
        )
        self.assertEqual(default_right_margin, 0)
        dialog.reject()

    def test_keep_and_optional_default_are_globally_synchronized(self):
        dialog = self._dialog(self._draft([
            self._poster("one.jpg"),
            self._poster("two.jpg"),
        ]))

        dialog._default_clicked("poster:one.jpg")
        self.assertEqual(dialog.default_key, "poster:one.jpg")
        self.assertTrue(dialog.cards["poster:one.jpg"].default_radio.isChecked())

        dialog._default_clicked("poster:two.jpg")
        self.assertEqual(dialog.default_key, "poster:two.jpg")
        self.assertFalse(dialog.cards["poster:one.jpg"].default_radio.isChecked())

        dialog._default_clicked("poster:two.jpg")
        self.assertIsNone(dialog.default_key)
        dialog._keep_changed("poster:one.jpg", False)
        self.assertFalse(dialog.cards["poster:one.jpg"].default_radio.isVisible())
        dialog.reject()

    def test_clicking_poster_opens_larger_preview_without_changing_selection(self):
        dialog = self._dialog(self._draft([self._poster("one.jpg")]))
        card = dialog.cards["poster:one.jpg"]
        selected_before = set(dialog.selected_keys)

        self.assertEqual(card.preview.toolTip(), "Open larger preview")
        self.assertEqual(
            card.preview.cursor().shape(),
            Qt.CursorShape.PointingHandCursor,
        )
        with patch(
            "app.media_details.poster_dialog.PosterPreviewDialog"
        ) as preview_dialog_class:
            QTest.mouseClick(card.preview, Qt.MouseButton.LeftButton)

        preview_dialog_class.assert_called_once()
        preview_dialog_class.return_value.exec.assert_called_once_with()
        self.assertEqual(dialog.selected_keys, selected_before)
        dialog.reject()

    def test_larger_remote_preview_uses_high_resolution_loader(self):
        loader = FakePreviewLoader()
        poster = self._poster("large.jpg")
        dialog = PosterPreviewDialog(None, poster, preview_loader=loader)
        dialog.show()
        self.application.processEvents()

        self.assertEqual(LARGE_POSTER_PREVIEW_SIZE, "w780")
        self.assertEqual(loader.requested, ["large.jpg"])
        pixmap = QPixmap(780, 1170)
        pixmap.fill(Qt.GlobalColor.blue)
        loader.poster_loaded.emit("preview:large.jpg", pixmap)
        self.application.processEvents()

        rendered = dialog.image_label.pixmap()
        self.assertFalse(rendered.isNull())
        self.assertGreater(rendered.width(), MANAGE_POSTER_WIDTH)
        self.assertLessEqual(rendered.width(), dialog.image_label.width())
        self.assertLessEqual(rendered.height(), dialog.image_label.height())
        dialog.reject()

    def test_larger_import_preview_loads_original_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "original.png"
            image = QImage(400, 600, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.blue)
            self.assertTrue(image.save(str(source)))
            loader = FakePreviewLoader()
            poster = {
                **self._poster("user-original.png"),
                "source": "user",
                "_import_path": str(source),
            }

            dialog = PosterPreviewDialog(None, poster, preview_loader=loader)
            dialog.show()
            self.application.processEvents()

            self.assertEqual(loader.requested, [])
            self.assertEqual(dialog.source_pixmap.size().width(), 400)
            self.assertEqual(dialog.source_pixmap.size().height(), 600)
            self.assertFalse(dialog.image_label.pixmap().isNull())
            dialog.reject()

    def test_discovery_deduplicates_database_filename(self):
        dialog = self._dialog(self._draft([self._poster("saved.jpg")]))
        dialog.discover_posters()
        self.manager.succeeded.emit(
            "job-1",
            {
                "posters": [
                    self._poster("saved.jpg"),
                    self._poster("new.jpg"),
                ],
                "checked_at": "2026-08-15T10:00:00+00:00",
            },
        )
        self.manager.finished.emit("job-1", {"status": "succeeded"})

        self.assertEqual(
            sorted(poster["filename"] for poster in dialog.candidates),
            ["new.jpg", "saved.jpg"],
        )
        self.assertNotIn("poster:new.jpg", dialog.selected_keys)
        self.assertEqual(dialog.checked_at, "2026-08-15T10:00:00+00:00")
        dialog.reject()

    def test_discovery_failure_is_inline_and_retryable(self):
        dialog = self._dialog(self._draft([]))
        dialog.discover_posters()
        self.manager.failed.emit("job-1", {"message": "offline"})
        self.manager.finished.emit("job-1", {"status": "failed"})
        self.assertTrue(dialog.feedback_frame.isVisible() or not dialog.isVisible())
        self.assertIn("offline", dialog.feedback_label.text())
        self.assertFalse(dialog.retry_button.isHidden())

        dialog.discover_posters()
        self.assertEqual(len(self.manager.started), 2)
        dialog.reject()

    def test_import_is_staged_deduplicated_and_saved_only_to_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "custom.png"
            image = QImage(20, 30, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.blue)
            self.assertTrue(image.save(str(source)))
            dialog = self._dialog(self._draft([]))

            with patch(
                "app.media_details.poster_dialog.QFileDialog.getOpenFileName",
                return_value=(str(source), ""),
            ):
                dialog.import_poster()
                dialog.import_poster()

            imports = [
                poster
                for poster in dialog.candidates
                if poster.get("_management_origin") == "import"
            ]
            self.assertEqual(len(imports), 1)
            self.assertIn(imports[0]["_import_path"], str(source))
            self.assertIn(f"poster:{imports[0]['filename']}", dialog.selected_keys)
            self.assertFalse((Path(temp_dir) / imports[0]["filename"]).exists())

            dialog.save()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            self.assertEqual(dialog.result_payload["status"], "saved")
            self.assertEqual(len(dialog.result_payload["posters"]), 1)

    def test_saved_management_state_reopens_with_removed_candidate_unchecked(self):
        dialog = self._dialog(self._draft([
            self._poster("keep.jpg"),
            self._poster("remove.jpg"),
        ]))
        dialog._keep_changed("poster:remove.jpg", False)
        dialog.save()
        draft = self._draft(dialog.result_payload["posters"])
        draft["_poster_management"] = dialog.result_payload["management_state"]

        reopened = self._dialog(draft)
        self.assertIn("poster:remove.jpg", reopened.cards)
        self.assertFalse(reopened.cards["poster:remove.jpg"].keep_checkbox.isChecked())
        reopened.reject()

    def test_episode_inherited_candidates_do_not_override_direct_selection(self):
        draft = self._draft([
            self._poster("episode.jpg"),
            {**self._poster("season.jpg"), "scope": "season"},
        ])
        draft["metadata"]["media_type"] = "episode"
        dialog = self._dialog(draft)
        self.assertTrue(
            dialog.cards["poster:episode.jpg"].keep_checkbox.isChecked()
        )
        self.assertFalse(
            dialog.cards["poster:season.jpg"].keep_checkbox.isChecked()
        )

        dialog._keep_changed("poster:episode.jpg", False)
        dialog._keep_changed("poster:season.jpg", True)
        dialog.save()
        self.assertEqual(dialog.result_payload["posters"][0]["scope"], "media")

    def _dialog(self, draft):
        return ManagePostersDialog(
            None,
            draft,
            discovery_manager=self.manager,
            preview_loader=self.preview_loader,
            auto_discover=False,
        )

    def _draft(self, posters):
        return {
            "media_id": 1,
            "metadata": {
                "media_type": "movie",
                "tmdb_id": 42,
                "title": "Movie",
            },
            "posters": posters,
            "watch_providers": [],
            "user_data": {},
        }

    def _poster(self, filename, is_default=False):
        return {
            "scope": "media",
            "filename": filename,
            "source": "tmdb",
            "curation_status": "selected" if is_default else "pending",
            "is_default": is_default,
            "series_tmdb_id": None,
            "season_num": None,
        }


class PosterRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        self.conn.close()

    def test_replace_is_concurrent_and_reference_safe(self):
        media_id = self._insert_media(1, "movie")
        series_id = self._insert_media(2, "series")
        self.conn.execute(
            "INSERT INTO media_posters (media_id, filename, source, curation_status, is_default) VALUES (?, 'old.jpg', 'tmdb', 'pending', 0)",
            (media_id,),
        )
        self.conn.execute(
            "INSERT INTO season_posters (series_id, season_num, filename, source, curation_status, is_default) VALUES (?, 1, 'old.jpg', 'tmdb', 'pending', 0)",
            (series_id,),
        )
        baseline = media_repository.get_direct_media_posters(self.conn, media_id)

        saved = media_repository.replace_media_posters(
            self.conn,
            media_id,
            [{"filename": "new.jpg", "source": "user", "is_default": True}],
            expected_posters=baseline,
        )
        self.assertEqual(saved[0]["curation_status"], "selected")
        self.assertTrue(saved[0]["is_default"])
        self.assertTrue(
            media_repository.poster_filename_is_referenced(self.conn, "old.jpg")
        )

        with self.assertRaises(media_repository.ConcurrentEditError):
            media_repository.replace_media_posters(
                self.conn,
                media_id,
                [],
                expected_posters=baseline,
            )

    def test_episode_direct_posters_override_and_then_fall_back(self):
        series_id = self._insert_media(10, "series")
        episode_id = self._insert_media(11, "episode")
        self.conn.execute(
            "INSERT INTO episode_details (media_id, series_id, season_num, episode_num) VALUES (?, ?, 1, 1)",
            (episode_id, series_id),
        )
        self.conn.execute(
            "INSERT INTO media_posters (media_id, filename, source, curation_status, is_default) VALUES (?, 'series.jpg', 'tmdb', 'selected', 0)",
            (series_id,),
        )
        metadata = {
            "media_type": "episode",
            "tmdb_id": 11,
            "episode_details": {
                "series_tmdb_id": 10,
                "season_num": 1,
            },
        }
        self.assertEqual(
            media_repository.get_db_media_posters(self.conn, metadata)[0]["filename"],
            "series.jpg",
        )

        media_repository.replace_media_posters(
            self.conn,
            episode_id,
            [{"filename": "episode.jpg", "source": "user"}],
        )
        self.assertEqual(
            media_repository.get_db_media_posters(self.conn, metadata)[0]["filename"],
            "episode.jpg",
        )
        media_repository.replace_media_posters(self.conn, episode_id, [])
        self.assertEqual(
            media_repository.get_db_media_posters(self.conn, metadata)[0]["filename"],
            "series.jpg",
        )

    def _insert_media(self, tmdb_id, media_type):
        cursor = self.conn.execute(
            "INSERT INTO media (tmdb_id, media_type, title) VALUES (?, ?, ?)",
            (tmdb_id, media_type, f"{media_type} {tmdb_id}"),
        )
        return cursor.lastrowid


class ManagedPosterSaveTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.temp_dir = tempfile.TemporaryDirectory()
        self.poster_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_explicit_selection_is_not_limited_to_one_poster(self):
        draft = self._new_movie_draft([
            self._selected("one.jpg"),
            self._selected("two.jpg"),
        ])
        media_id = media_repository.save_media_draft(self.conn, draft)
        rows = media_repository.get_direct_media_posters(self.conn, media_id)
        self.assertEqual(
            [row["filename"] for row in rows],
            ["one.jpg", "two.jpg"],
        )

    def test_existing_save_materializes_import_and_replaces_posters(self):
        original = self._new_movie_draft([
            {
                **self._selected("old.jpg"),
                "curation_status": "pending",
            }
        ])
        media_id = media_repository.save_media_draft(self.conn, original)
        (self.poster_dir / "old.jpg").write_bytes(b"old-poster")
        baseline = draft_builder.build_media_draft_from_db(
            self.conn,
            media_repository.get_media_by_id(self.conn, media_id),
        )
        source = self.poster_dir / "outside-import.png"
        source.write_bytes(b"new-user-poster")
        content_hash = sha256(source.read_bytes()).hexdigest()
        imported_filename = f"user-{content_hash}.png"
        current = deepcopy(baseline)
        current["posters"] = [
            {**baseline["posters"][0], "curation_status": "selected"},
            {
                **self._selected(imported_filename, source="user"),
                "_import_path": str(source),
                "_content_hash": content_hash,
            },
        ]
        current["_poster_management"] = {
            "checked_at": "2026-08-15T10:00:00+00:00",
        }

        with self.conn:
            result = draft_saver.save_existing_media_changes(
                self.conn,
                baseline,
                current,
                poster_dir=self.poster_dir,
            )

        rows = media_repository.get_direct_media_posters(self.conn, media_id)
        self.assertEqual(
            {row["filename"] for row in rows},
            {"old.jpg", imported_filename},
        )
        self.assertTrue((self.poster_dir / imported_filename).is_file())
        self.assertIn(imported_filename, result["poster_files_created"])
        self.assertEqual(
            media_repository.get_media_by_id(self.conn, media_id)[
                "last_tmdb_posters_checked_at"
            ],
            "2026-08-15T10:00:00+00:00",
        )

    def test_missing_import_aborts_before_database_changes(self):
        original = self._new_movie_draft([])
        media_id = media_repository.save_media_draft(self.conn, original)
        baseline = draft_builder.build_media_draft_from_db(
            self.conn,
            media_repository.get_media_by_id(self.conn, media_id),
        )
        current = deepcopy(baseline)
        current["posters"] = [{
            **self._selected("user-missing.png", source="user"),
            "_import_path": str(self.poster_dir / "missing.png"),
            "_content_hash": "deadbeef",
        }]
        current["_poster_management"] = {"checked_at": None}

        with self.assertRaises(ValueError):
            with self.conn:
                draft_saver.save_existing_media_changes(
                    self.conn,
                    baseline,
                    current,
                    poster_dir=self.poster_dir,
                )
        self.assertEqual(
            media_repository.get_direct_media_posters(self.conn, media_id),
            [],
        )

    def _new_movie_draft(self, posters):
        return {
            "media_id": None,
            "metadata": {
                "tmdb_id": 500,
                "media_type": "movie",
                "title": "Movie 500",
                "genres": [],
                "spoken_languages": [],
                "production_countries": [],
                "production_companies": [],
                "directors": [],
                "creators": [],
                "writers": [],
                "actors": [],
            },
            "series_view": None,
            "watch_providers": [],
            "posters": posters,
            "user_data": {
                "watch_state": "to_watch",
                "impression": None,
                "is_collection_pick": None,
                "watch_history": [],
                "notes": [],
                "lists": [],
            },
        }

    def _selected(self, filename, source="tmdb"):
        return {
            "scope": "media",
            "filename": filename,
            "source": source,
            "curation_status": "selected",
            "is_default": False,
            "series_tmdb_id": None,
            "season_num": None,
        }


if __name__ == "__main__":
    unittest.main()
