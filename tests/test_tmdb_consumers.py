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

    def test_media_details_provider_reload_uses_tmdb_facade(self):
        dialog = SimpleNamespace(
            _metadata_refresh_in_progress=False,
            _is_dirty=False,
            media_draft={
                "media_id": None,
                "metadata": {"media_type": "movie", "tmdb_id": 7},
            },
            render_watch_providers=Mock(),
            _update_action_buttons=Mock(),
        )
        providers = [{"provider_name": "Example"}]

        with patch.object(
            details_dialog.tmdb,
            "get_tmdb_media_watch_providers",
            return_value=providers,
        ) as fetch_providers, patch.object(
            details_dialog,
            "current_freshness_timestamp",
            return_value="2026-08-09 12:00:00",
        ):
            details_dialog.MediaDetailsDialog.reload_watch_providers(dialog)

        fetch_providers.assert_called_once_with({
            "media_type": "movie",
            "tmdb_id": 7,
        })
        self.assertEqual(dialog.media_draft["watch_providers"], providers)
        self.assertEqual(
            dialog.media_draft["metadata"][
                "last_tmdb_watch_providers_checked_at"
            ],
            "2026-08-09 12:00:00",
        )
        self.assertTrue(dialog._is_dirty)
        dialog.render_watch_providers.assert_called_once_with()
        dialog._update_action_buttons.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
