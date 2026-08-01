import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QObject, QPoint, QSize, Signal, Qt
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMessageBox,
    QSizePolicy,
)

import app.match_selection_dialog as match_selection_dialog
from app.match_selection_dialog import MatchSelectionDialog, TmdbPosterLoader
from app.media_state_controls import ClickableEntryLabel
from app.top_bar import INPUT_BOX_STYLE, TopBar


class FakePosterLoader(QObject):
    poster_loaded = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.requested_paths = []

    def request(self, poster_path):
        self.requested_paths.append(poster_path)
        return match_selection_dialog._tmdb_poster_url(poster_path)

    def finish(self, poster_path, pixmap):
        self.poster_loaded.emit(
            match_selection_dialog._tmdb_poster_url(poster_path),
            pixmap,
        )


class FakeNetworkReply(QObject):
    finished = Signal()

    def __init__(self, payload, error=QNetworkReply.NetworkError.NoError):
        super().__init__()
        self.payload = payload
        self.network_error = error
        self.was_deleted = False

    def error(self):
        return self.network_error

    def readAll(self):
        return self.payload

    def deleteLater(self):
        self.was_deleted = True


class MatchSelectionDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.application.processEvents()

    def test_builds_modal_two_column_dialog_with_local_and_remote_posters(self):
        with TemporaryDirectory() as directory:
            poster_path = Path(directory) / "robin.png"
            image = QImage(20, 30, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.red)
            self.assertTrue(image.save(str(poster_path)))

            candidates = [
                self._candidate(
                    1,
                    "movie",
                    "Robin Hood",
                    source="db",
                    poster_path=poster_path.name,
                    remote_poster_path="/unused-remote.jpg",
                    release_date="2010-05-12",
                ),
                self._candidate(
                    2,
                    "series",
                    "Robin Hood",
                    source="tmdb",
                    poster_path="/remote.jpg",
                    release_date="2018-01-01",
                ),
            ]

            with patch.object(
                match_selection_dialog,
                "POSTER_DIR",
                Path(directory),
            ):
                dialog = self._dialog(candidates=candidates)

            self.assertEqual(dialog.windowTitle(), "Match Selection")
            self.assertTrue(dialog.isModal())
            self.assertTrue(dialog.find_media_input.isClearButtonEnabled())
            self.assertIsNot(dialog.movie_scroll, dialog.series_scroll)
            self.assertEqual(
                dialog.movie_scroll.verticalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAsNeeded,
            )
            self.assertEqual(len(dialog.movie_candidate_widgets), 1)
            self.assertEqual(len(dialog.series_candidate_widgets), 1)

            local_row = dialog.movie_candidate_widgets[0]
            remote_row = dialog.series_candidate_widgets[0]
            self.assertIsInstance(local_row.title_label, ClickableEntryLabel)
            self.assertFalse(local_row.poster_label.pixmap().isNull())
            self.assertEqual(local_row.year_label.text(), "2010")
            self.assertTrue(remote_row.poster_label.pixmap().isNull())
            self.assertEqual(remote_row.poster_label.text(), "Loading…")
            self.assertEqual(
                dialog.poster_loader.requested_paths,
                ["/remote.jpg"],
            )

            remote_pixmap = local_row.poster_label.pixmap()
            dialog.poster_loader.finish("/remote.jpg", remote_pixmap)

            self.assertFalse(remote_row.poster_label.pixmap().isNull())
            self.assertEqual(remote_row.poster_label.text(), "")

    def test_uses_main_window_dimensions_typography_and_control_sizes(self):
        dialog = self._dialog()
        top_bar = TopBar()
        self.addCleanup(top_bar.close)

        self.assertEqual(dialog.size(), QSize(900, 680))
        self.assertEqual(dialog.minimumSize(), QSize(900, 600))

        dialog.show()
        top_bar.show()
        self.application.processEvents()
        baseline_height = top_bar.find_media_label.fontMetrics().height()

        self.assertEqual(dialog.find_media_input.height(), 32)
        self.assertEqual(dialog.find_media_input.styleSheet(), INPUT_BOX_STYLE)
        self.assertEqual(
            dialog.find_media_label.fontMetrics().height(),
            baseline_height,
        )
        self.assertEqual(
            dialog.find_media_input.fontMetrics().height(),
            top_bar.find_media_input.fontMetrics().height(),
        )
        self.assertEqual(
            dialog.instruction_label.fontMetrics().height(),
            baseline_height,
        )

        column_titles = dialog.findChildren(QLabel, "matchColumnTitle")
        self.assertEqual(len(column_titles), 2)

        for label in column_titles:
            self.assertEqual(label.fontMetrics().height(), baseline_height)

        candidate_row = dialog.movie_candidate_widgets[0]
        self.assertEqual(
            candidate_row.title_label.fontMetrics().height(),
            baseline_height,
        )
        self.assertTrue(candidate_row.title_label.font().bold())
        self.assertEqual(
            candidate_row.year_label.fontMetrics().height(),
            baseline_height,
        )
        self.assertEqual(dialog.cancel_button.width(), 100)
        self.assertEqual(dialog.cancel_button.minimumHeight(), 32)
        self.assertEqual(
            dialog.cancel_button.fontMetrics().height(),
            baseline_height,
        )
        self.assertNotIn(
            "font-size",
            match_selection_dialog.MATCH_SELECTION_STYLE,
        )

    def test_candidate_columns_use_history_native_independent_scrollbars(self):
        candidates = [
            self._candidate(index, "movie", f"Movie {index}")
            for index in range(1, 9)
        ] + [
            self._candidate(index, "series", f"Series {index}")
            for index in range(20, 28)
        ]
        dialog = self._dialog(candidates=candidates)
        dialog.show()
        self.application.processEvents()

        movie_bar = dialog.movie_scroll.verticalScrollBar()
        series_bar = dialog.series_scroll.verticalScrollBar()

        for scroll in (dialog.movie_scroll, dialog.series_scroll):
            self.assertEqual(
                scroll.verticalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAsNeeded,
            )
            self.assertEqual(
                scroll.horizontalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.assertEqual(
                scroll.viewport().objectName(),
                "matchCandidateScrollViewport",
            )

        self.assertNotIn(
            "QScrollBar",
            match_selection_dialog.MATCH_SELECTION_STYLE,
        )
        self.assertNotIn(
            "> QWidget",
            match_selection_dialog.MATCH_SELECTION_STYLE,
        )

        self.assertGreater(movie_bar.maximum(), 0)
        self.assertGreater(series_bar.maximum(), 0)
        movie_bar.setValue(min(100, movie_bar.maximum()))
        self.assertGreater(movie_bar.value(), 0)
        self.assertEqual(series_bar.value(), 0)

    def test_candidate_rows_keep_posters_top_aligned_at_any_result_count(self):
        scenarios = [
            [
                self._candidate(1, "movie", "Only Movie"),
                self._candidate(2, "series", "Only Series"),
            ],
            [
                *[
                    self._candidate(index, "movie", f"Movie {index}")
                    for index in range(10, 13)
                ],
                *[
                    self._candidate(index, "series", f"Series {index}")
                    for index in range(20, 23)
                ],
            ],
        ]

        for candidates in scenarios:
            with self.subTest(candidate_count=len(candidates)):
                dialog = self._dialog(candidates=candidates)
                dialog.show()
                self.application.processEvents()

                rows = [
                    *dialog.movie_candidate_widgets,
                    *dialog.series_candidate_widgets,
                ]

                for row in rows:
                    top_margin = row.layout().contentsMargins().top()
                    self.assertEqual(
                        row.sizePolicy().verticalPolicy(),
                        QSizePolicy.Policy.Fixed,
                    )
                    self.assertEqual(row.height(), row.sizeHint().height())
                    self.assertEqual(row.poster_label.y(), top_margin)

    def test_remote_poster_failure_falls_back_to_placeholder(self):
        candidate = self._candidate(
            2,
            "series",
            poster_path="/missing.jpg",
        )
        dialog = self._dialog(candidates=[candidate])
        row = dialog.series_candidate_widgets[0]

        self.assertEqual(row.poster_label.text(), "Loading…")
        dialog.poster_loader.finish("/missing.jpg", None)

        self.assertEqual(row.poster_label.text(), "No poster")
        self.assertTrue(row.poster_label.pixmap().isNull())

    def test_db_candidate_uses_preserved_remote_poster_when_local_is_missing(self):
        candidate = self._candidate(
            3,
            "movie",
            source="db",
            poster_path="missing-local.jpg",
            remote_poster_path="/remote-fallback.jpg",
        )
        dialog = self._dialog(candidates=[candidate])

        self.assertEqual(
            dialog.poster_loader.requested_paths,
            ["/remote-fallback.jpg"],
        )
        self.assertEqual(
            dialog.movie_candidate_widgets[0].poster_label.text(),
            "Loading…",
        )

    def test_tmdb_poster_url_uses_smallest_size_without_double_slash(self):
        self.assertEqual(
            match_selection_dialog._tmdb_poster_url("/poster.jpg"),
            "https://image.tmdb.org/t/p/w92/poster.jpg",
        )

    def test_tmdb_poster_loader_decodes_and_caches_successful_response(self):
        reply = FakeNetworkReply(self._png_bytes())
        network_manager = Mock()
        network_manager.get.return_value = reply
        loader = TmdbPosterLoader(network_manager=network_manager)
        loaded = []
        loader.poster_loaded.connect(
            lambda url, pixmap: loaded.append((url, pixmap))
        )

        loader.request("/poster.png")

        request = network_manager.get.call_args.args[0]
        self.assertEqual(
            request.url().toString(),
            "https://image.tmdb.org/t/p/w92/poster.png",
        )
        self.assertEqual(request.transferTimeout(), 8_000)

        reply.finished.emit()

        self.assertTrue(reply.was_deleted)
        self.assertEqual(len(loaded), 1)
        self.assertFalse(loaded[0][1].isNull())

        loader.request("/poster.png")

        network_manager.get.assert_called_once()
        self.assertEqual(len(loaded), 2)
        self.assertFalse(loaded[1][1].isNull())

    def test_tmdb_poster_loader_handles_network_failure(self):
        reply = FakeNetworkReply(
            b"",
            QNetworkReply.NetworkError.ContentNotFoundError,
        )
        network_manager = Mock()
        network_manager.get.return_value = reply
        loader = TmdbPosterLoader(network_manager=network_manager)
        loaded = []
        loader.poster_loaded.connect(
            lambda url, pixmap: loaded.append((url, pixmap))
        )

        loader.request("/missing.jpg")
        reply.finished.emit()

        self.assertTrue(reply.was_deleted)
        self.assertEqual(
            loaded,
            [("https://image.tmdb.org/t/p/w92/missing.jpg", None)],
        )

    def test_simultaneous_duplicate_posters_share_one_network_request(self):
        reply = FakeNetworkReply(self._png_bytes())
        network_manager = Mock()
        network_manager.get.return_value = reply
        loader = TmdbPosterLoader(network_manager=network_manager)
        candidates = [
            self._candidate(1, "movie", poster_path="/shared.png"),
            self._candidate(2, "series", poster_path="/shared.png"),
        ]

        dialog = self._dialog(
            candidates=candidates,
            poster_loader=loader,
        )

        network_manager.get.assert_called_once()
        reply.finished.emit()

        self.assertFalse(
            dialog.movie_candidate_widgets[0].poster_label.pixmap().isNull()
        )
        self.assertFalse(
            dialog.series_candidate_widgets[0].poster_label.pixmap().isNull()
        )

    def test_clicking_title_selects_candidate(self):
        candidate = self._candidate(1, "movie", "Robin Hood")
        dialog = self._dialog(candidates=[candidate, self._candidate(2, "series")])
        dialog.show()
        self.application.processEvents()

        title_label = dialog.movie_candidate_widgets[0].title_label
        QTest.mouseClick(
            title_label,
            Qt.MouseButton.LeftButton,
            pos=QPoint(2, title_label.height() // 2),
        )

        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(
            dialog.result_payload,
            {"status": "selected", "candidate": candidate},
        )

    def test_enter_and_space_on_title_select_candidate(self):
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            with self.subTest(key=key):
                candidate = self._candidate(1, "movie", "Robin Hood")
                dialog = self._dialog(
                    candidates=[candidate, self._candidate(2, "series")]
                )
                title_label = dialog.movie_candidate_widgets[0].title_label
                title_label.setFocus(Qt.FocusReason.TabFocusReason)

                QTest.keyClick(title_label, key)

                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                self.assertEqual(dialog.result_payload["candidate"], candidate)

    def test_enter_closes_dialog_and_requests_full_find_media_restart(self):
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            with self.subTest(key=key):
                dialog = self._dialog()
                dialog.show()
                dialog.find_media_input.setText("  refined query  ")
                dialog.find_media_input.setFocus()
                self.application.processEvents()

                self.assertFalse(dialog.cancel_button.autoDefault())
                self.assertFalse(dialog.cancel_button.isDefault())

                QTest.keyClick(dialog.find_media_input, key)
                self.application.processEvents()

                self.assertEqual(
                    dialog.result(),
                    QDialog.DialogCode.Accepted,
                )
                self.assertEqual(
                    dialog.result_payload,
                    {"status": "restart", "query": "refined query"},
                )

    def test_empty_refinement_warns_without_closing_or_replacing_candidates(self):
        original_candidates = [
            self._candidate(1, "movie"),
            self._candidate(2, "series"),
        ]
        dialog = self._dialog(
            candidates=original_candidates,
        )
        dialog.show()
        dialog.find_media_input.setText("   ")
        dialog.find_media_input.setFocus()
        self.application.processEvents()

        with patch.object(QMessageBox, "warning") as warning:
            QTest.keyClick(dialog.find_media_input, Qt.Key.Key_Return)
            self.application.processEvents()

        self.assertIn("Enter an IMDb ID", warning.call_args.args[2])
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.candidates, original_candidates)
        self.assertEqual(dialog.result_payload, {"status": "cancelled"})

    def test_cancel_rejects_and_keeps_cancelled_payload(self):
        dialog = self._dialog()

        dialog.cancel_button.click()

        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertEqual(dialog.result_payload, {"status": "cancelled"})

    def _dialog(
        self,
        candidates=None,
        poster_loader=None,
    ):
        candidates = candidates or [
            self._candidate(1, "movie", "Robin Hood"),
            self._candidate(2, "series", "Robin Hood"),
        ]
        poster_loader = poster_loader or FakePosterLoader()
        dialog = MatchSelectionDialog(
            parent=None,
            query="robin hood",
            candidates=candidates,
            poster_loader=poster_loader,
        )
        self.addCleanup(dialog.close)
        return dialog

    @staticmethod
    def _candidate(
        tmdb_id,
        media_type,
        title="Robin Hood",
        *,
        source="tmdb",
        poster_path=None,
        remote_poster_path=None,
        release_date="2025-01-01",
    ):
        return {
            "source": source,
            "media_id": tmdb_id if source == "db" else None,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "imdb_id": None,
            "title": title,
            "original_title": title,
            "localized_titles": [],
            "alternate_titles": [],
            "release_date": release_date,
            "poster_path": poster_path,
            "remote_poster_path": remote_poster_path,
        }

    @staticmethod
    def _png_bytes():
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "poster.png"
            image = QImage(20, 30, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.blue)

            if not image.save(str(image_path)):
                raise AssertionError("Could not create the poster test fixture.")

            return image_path.read_bytes()


if __name__ == "__main__":
    unittest.main()
