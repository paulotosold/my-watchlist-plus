from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import app.media_draft.poster_storage as poster_storage
import app.media_details.dialog as details_dialog


class TmdbConsumerBoundaryTests(unittest.TestCase):
    def test_poster_download_uses_shared_cdn_url_builder(self):
        response = Mock()
        response.iter_content.return_value = [b"poster-bytes"]

        with TemporaryDirectory() as temp_dir, patch.object(
            poster_storage.tmdb,
            "build_tmdb_image_url",
            return_value="https://image.test/w185/poster.jpg",
        ) as build_url, patch.object(
            poster_storage.requests,
            "get",
            return_value=response,
        ) as get_mock:
            poster_path = poster_storage.download_tmdb_poster(
                "/poster.jpg",
                poster_dir=temp_dir,
                poster_size="w185",
            )

            self.assertEqual(poster_path.read_bytes(), b"poster-bytes")

        build_url.assert_called_once_with("poster.jpg", size="w185")
        get_mock.assert_called_once_with(
            "https://image.test/w185/poster.jpg",
            stream=True,
            timeout=30,
        )
        response.raise_for_status.assert_called_once_with()

    def test_media_details_preview_uses_shared_cdn_url_builder(self):
        response = Mock(content=b"preview-bytes")
        pixmap = Mock()
        pixmap.loadFromData.return_value = True

        with TemporaryDirectory() as temp_dir, patch.object(
            details_dialog,
            "POSTER_DIR",
            Path(temp_dir),
        ), patch.object(
            details_dialog.tmdb,
            "build_tmdb_image_url",
            return_value="https://image.test/w185/poster.jpg",
        ) as build_url, patch.object(
            details_dialog.requests,
            "get",
            return_value=response,
        ) as get_mock, patch.object(
            details_dialog,
            "QPixmap",
            return_value=pixmap,
        ):
            result = details_dialog.load_poster_pixmap({
                "filename": "/poster.jpg",
                "source": "tmdb",
            })

        self.assertIs(result, pixmap)
        build_url.assert_called_once_with("poster.jpg", size="w185")
        get_mock.assert_called_once_with(
            "https://image.test/w185/poster.jpg",
            timeout=8,
        )
        response.raise_for_status.assert_called_once_with()
        pixmap.loadFromData.assert_called_once_with(b"preview-bytes")

    def test_media_details_provider_reload_uses_background_manager(self):
        refresh_manager = Mock()
        refresh_manager.start_refresh.return_value = "provider-job"
        dialog = SimpleNamespace(
            _metadata_refresh_in_progress=False,
            _watch_provider_refresh_in_progress=False,
            media_draft={
                "media_id": None,
                "metadata": {"media_type": "movie", "tmdb_id": 7},
            },
            watch_provider_refresh_manager=refresh_manager,
            _hide_watch_provider_refresh_feedback=Mock(),
            _set_watch_provider_refresh_busy=Mock(),
            _show_watch_provider_refresh_feedback=Mock(),
        )

        details_dialog.MediaDetailsDialog.reload_watch_providers(dialog)

        refresh_manager.start_refresh.assert_called_once_with(
            None,
            {"media_type": "movie", "tmdb_id": 7},
        )
        self.assertEqual(dialog._watch_provider_refresh_job_id, "provider-job")
        self.assertIsNone(dialog._watch_provider_refresh_target_media_id)
        self.assertTrue(dialog._watch_provider_refresh_is_manual)
        self.assertFalse(
            dialog._watch_provider_refresh_completed_successfully
        )
        dialog._set_watch_provider_refresh_busy.assert_called_once_with(True)
        dialog._show_watch_provider_refresh_feedback.assert_called_once_with(
            "Fetching providers…"
        )


if __name__ == "__main__":
    unittest.main()
