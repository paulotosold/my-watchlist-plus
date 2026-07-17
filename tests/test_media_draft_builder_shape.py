import os
import unittest
from unittest.mock import patch


os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")

import app.media_draft_builder as media_draft_builder


CANONICAL_DRAFT_KEYS = {
    "media_id",
    "metadata",
    "series_view",
    "watch_providers",
    "posters",
    "user_data",
}


class MediaDraftBuilderShapeTests(unittest.TestCase):
    def test_tmdb_builders_keep_the_six_canonical_top_level_keys(self):
        for media_type in ("movie", "series", "episode"):
            with self.subTest(media_type=media_type), patch.object(
                media_draft_builder.app.tmdb_fetcher,
                "get_tmdb_media_metadata",
                return_value={"tmdb_id": 42, "media_type": media_type},
            ), patch.object(
                media_draft_builder.app.tmdb_fetcher,
                "get_tmdb_media_series_view",
                return_value={} if media_type == "series" else None,
            ), patch.object(
                media_draft_builder.app.tmdb_fetcher,
                "get_tmdb_media_watch_providers",
                return_value=[],
            ), patch.object(
                media_draft_builder.app.tmdb_fetcher,
                "get_tmdb_media_posters",
                return_value=[],
            ), patch.object(
                media_draft_builder.app.tmdb_fetcher,
                "get_tmdb_media_user_data",
                return_value={},
            ), patch.object(
                media_draft_builder.app.tmdb_fetcher,
                "current_sqlite_timestamp",
                return_value="2026-07-17 12:00:00",
            ):
                draft = media_draft_builder.build_media_draft_from_tmdb_match({
                    "tmdb_id": 42,
                    "media_type": media_type,
                })

            self.assertEqual(set(draft), CANONICAL_DRAFT_KEYS)

            if media_type == "movie":
                self.assertEqual(
                    draft["metadata"]["last_tmdb_posters_checked_at"],
                    "2026-07-17 12:00:00",
                )
            else:
                self.assertIsNone(
                    draft["metadata"]["last_tmdb_posters_checked_at"]
                )

    def test_db_builder_keeps_the_six_canonical_top_level_keys(self):
        media_from_db = {"id": 7}

        with patch.object(
            media_draft_builder.media_repo,
            "get_db_media_metadata",
            return_value={"media_type": "series"},
        ), patch.object(
            media_draft_builder.media_repo,
            "get_db_series_view",
            return_value={},
        ), patch.object(
            media_draft_builder.media_repo,
            "get_db_media_watch_providers",
            return_value=[],
        ), patch.object(
            media_draft_builder.media_repo,
            "get_db_media_posters",
            return_value=[],
        ), patch.object(
            media_draft_builder.media_repo,
            "get_db_media_user_data",
            return_value={},
        ):
            draft = media_draft_builder.build_media_draft_from_db(
                object(),
                media_from_db,
            )

        self.assertEqual(set(draft), CANONICAL_DRAFT_KEYS)


if __name__ == "__main__":
    unittest.main()
