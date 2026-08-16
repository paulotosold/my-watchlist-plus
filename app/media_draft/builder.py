"""Build canonical media-draft dictionaries from database or TMDB data."""

import app.media_repository as media_repo
import app.tmdb as tmdb
from app.tmdb import current_freshness_timestamp


def build_media_draft_from_db(conn, media_from_db):
    metadata = media_repo.get_db_media_metadata(conn, media_from_db)
    series_view = media_repo.get_db_series_view(
        conn,
        media_from_db["id"],
        metadata["media_type"],
    )
    watch_providers = media_repo.get_db_media_watch_providers(conn, metadata)
    posters = media_repo.get_db_media_posters(conn, metadata)
    user_data = media_repo.get_db_media_user_data(conn, metadata)

    return {
        "media_id": media_from_db["id"],
        "metadata": metadata,
        "series_view": series_view,
        "watch_providers": watch_providers,
        "posters": posters,
        "user_data": user_data,
    }


def build_media_draft_from_tmdb(imdb_id):
    tmdb_match = tmdb.find_tmdb_match_by_imdb_id(imdb_id)

    if tmdb_match["status"] != "resolved":
        raise ValueError(tmdb_match.get("reason") or "TMDB match was not resolved.")

    media_draft = build_media_draft_from_tmdb_match(tmdb_match)
    metadata = media_draft["metadata"]

    if not metadata.get("imdb_id"):
        metadata["imdb_id"] = imdb_id

    return media_draft


def build_media_draft_from_tmdb_match(tmdb_match):
    checked_at = current_freshness_timestamp()
    metadata = tmdb.get_tmdb_media_metadata(tmdb_match)
    metadata["last_tmdb_metadata_checked_at"] = checked_at
    metadata["last_tmdb_watch_providers_checked_at"] = checked_at
    series_view = tmdb.get_tmdb_media_series_view(tmdb_match)

    if series_view is not None:
        series_view["episode_watch_history"] = []

    watch_providers = tmdb.get_tmdb_media_watch_providers(tmdb_match)
    posters = tmdb.get_tmdb_media_posters(tmdb_match)[:1]
    metadata["last_tmdb_posters_checked_at"] = (
        checked_at
        if metadata.get("media_type") == "movie"
        else None
    )

    return {
        "media_id": None,
        "metadata": metadata,
        "series_view": series_view,
        "watch_providers": watch_providers,
        "posters": posters,
        "user_data": _new_media_user_data(),
    }


def _new_media_user_data():
    return {
        "watch_state": "to_watch",
        "impression": None,
        "is_cabinet_worthy": None,
        "cabinet_order": None,
        "watch_history": [],
        "notes": [],
        "lists": [],
    }
