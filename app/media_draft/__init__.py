"""Public API for building, transforming, and saving media drafts."""

from .builder import (
    build_media_draft_from_db,
    build_media_draft_from_tmdb,
    build_media_draft_from_tmdb_match,
)
from .poster_storage import (
    DEFAULT_POSTER_DIR,
    download_missing_draft_posters,
    download_tmdb_poster,
    limit_draft_posters,
)
from .saver import (
    build_and_save_media_drafts_from_imdb_ids,
    save_existing_media_changes,
    save_media_draft_with_posters,
)
from .state import apply_inserted_ids_to_draft, merge_metadata_refresh


__all__ = [
    "DEFAULT_POSTER_DIR",
    "apply_inserted_ids_to_draft",
    "build_and_save_media_drafts_from_imdb_ids",
    "build_media_draft_from_db",
    "build_media_draft_from_tmdb",
    "build_media_draft_from_tmdb_match",
    "download_missing_draft_posters",
    "download_tmdb_poster",
    "limit_draft_posters",
    "merge_metadata_refresh",
    "save_existing_media_changes",
    "save_media_draft_with_posters",
]
