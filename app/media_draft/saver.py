"""Persist media drafts and materialize their related catalog context."""

import app.media_repository as media_repository
import app.tmdb as tmdb
from app.config import TMDB_MAX_POSTERS_PER_MEDIA, TMDB_POSTER_SIZE
from app.tmdb import current_freshness_timestamp

from . import builder, poster_storage


DEFAULT_POSTER_DIR = poster_storage.DEFAULT_POSTER_DIR
POSTER_MANAGEMENT_KEY = "_poster_management"


def build_and_save_media_drafts_from_imdb_ids(
    conn,
    imdb_ids,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
    fetch_episode_imdb_ids=True,
):
    results = []

    for imdb_id in imdb_ids:
        imdb_id = imdb_id.strip()

        if not imdb_id:
            continue

        try:
            media_draft = builder.build_media_draft_from_tmdb(imdb_id)
            with conn:
                save_result = save_media_draft_with_posters(
                    conn,
                    media_draft,
                    poster_dir=poster_dir,
                    poster_size=poster_size,
                    max_posters_per_media=max_posters_per_media,
                    fail_on_poster_error=fail_on_poster_error,
                    fetch_episode_imdb_ids=fetch_episode_imdb_ids,
                )

            metadata = media_draft["metadata"]

            results.append({
                "status": "saved",
                "imdb_id": imdb_id,
                "media_id": save_result["media_id"],
                "media_type": save_result.get(
                    "saved_media_type",
                    metadata.get("media_type"),
                ),
                "title": save_result.get("saved_title", metadata.get("title")),
                "poster_downloads": save_result["poster_downloads"],
                "series_completed": save_result.get("series_completed", False),
                "saved_original_episode": save_result.get(
                    "saved_original_episode",
                    True,
                ),
            })
        except Exception as exc:
            conn.rollback()
            results.append({
                "status": "error",
                "imdb_id": imdb_id,
                "error": str(exc),
            })

    return results


def save_media_draft_with_posters(
    conn,
    media_draft,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
    fetch_episode_imdb_ids=True,
):
    _normalize_managed_episode_posters(media_draft)
    management_state = media_draft.get(POSTER_MANAGEMENT_KEY) or {}
    if management_state.get("checked_at"):
        media_draft.setdefault("metadata", {})[
            "last_tmdb_posters_checked_at"
        ] = management_state["checked_at"]

    if media_draft["metadata"].get("media_type") == "episode":
        return _save_episode_draft_with_series_context(
            conn,
            media_draft,
            poster_dir=poster_dir,
            poster_size=poster_size,
            max_posters_per_media=max_posters_per_media,
            fail_on_poster_error=fail_on_poster_error,
            fetch_episode_imdb_ids=fetch_episode_imdb_ids,
        )

    if media_draft["metadata"].get("media_type") == "series":
        return _save_series_draft_with_episode_context(
            conn,
            media_draft,
            poster_dir=poster_dir,
            poster_size=poster_size,
            max_posters_per_media=max_posters_per_media,
            fail_on_poster_error=fail_on_poster_error,
            fetch_episode_imdb_ids=fetch_episode_imdb_ids,
        )

    return _save_single_media_draft_with_posters(
        conn,
        media_draft,
        poster_dir=poster_dir,
        poster_size=poster_size,
        max_posters_per_media=max_posters_per_media,
        fail_on_poster_error=fail_on_poster_error,
    )


def save_existing_media_changes(
    conn,
    baseline_draft,
    media_draft,
    *,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
):
    """Persist user-owned and explicitly curated poster changes.

    Catalog metadata, providers, and series episode materialization remain
    outside this path. The caller owns the transaction.
    """
    media_id = media_draft.get("media_id")

    if media_id is None or baseline_draft.get("media_id") != media_id:
        raise ValueError("Existing-media save requires matching media ids.")

    management_state = media_draft.get(POSTER_MANAGEMENT_KEY)
    poster_downloads = poster_storage._empty_poster_downloads()
    created_user_files = []
    files_to_delete = []

    try:
        if management_state is not None:
            _normalize_managed_episode_posters(media_draft)
            created_user_files = poster_storage.materialize_user_posters(
                media_draft,
                poster_dir=poster_dir,
            )
            poster_downloads = poster_storage.download_missing_draft_posters(
                media_draft,
                poster_dir=poster_dir,
                poster_size=poster_size,
                fail_on_error=True,
            )

        result = media_repository.apply_media_user_changes(
            conn,
            media_id,
            baseline_draft,
            media_draft,
        )

        if management_state is not None:
            expected_posters = [
                poster
                for poster in baseline_draft.get("posters", [])
                if poster.get("scope", "media") == "media"
            ]
            current_posters = list(media_draft.get("posters", []))
            media_repository.replace_media_posters(
                conn,
                media_id,
                current_posters,
                expected_posters=expected_posters,
                checked_at=management_state.get("checked_at"),
            )
            if management_state.get("checked_at"):
                media_draft.setdefault("metadata", {})[
                    "last_tmdb_posters_checked_at"
                ] = management_state["checked_at"]
            current_filenames = {
                poster.get("filename")
                for poster in current_posters
                if poster.get("filename")
            }
            files_to_delete = [
                poster.get("filename")
                for poster in expected_posters
                if (
                    poster.get("filename")
                    and poster.get("filename") not in current_filenames
                )
            ]
    except Exception:
        poster_storage.cleanup_created_poster_files(
            created_user_files + poster_downloads.get("downloaded", []),
            poster_dir=poster_dir,
        )
        raise

    metadata = media_draft.get("metadata") or {}
    return {
        **result,
        "media_id": media_id,
        "poster_downloads": poster_downloads,
        "poster_files_created": (
            created_user_files + poster_downloads.get("downloaded", [])
        ),
        "poster_files_to_delete": files_to_delete,
        "saved_media_type": metadata.get("media_type"),
        "saved_title": metadata.get("title"),
    }


def _save_episode_draft_with_series_context(
    conn,
    media_draft,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
    fetch_episode_imdb_ids=True,
):
    managed_checked_at = (
        (media_draft.get(POSTER_MANAGEMENT_KEY) or {}).get("checked_at")
    )
    episode_details = media_draft["metadata"].get("episode_details") or {}
    series_tmdb_id = episode_details.get("series_tmdb_id")

    if series_tmdb_id is None:
        raise ValueError("Episode draft requires episode_details.series_tmdb_id.")

    poster_downloads = poster_storage._empty_poster_downloads()
    series_created = False

    series = media_repository.get_media_by_tmdb_id(
        conn,
        series_tmdb_id,
        "series",
    )
    existing_episode = media_repository.get_media_by_tmdb_id(
        conn,
        media_draft["metadata"].get("tmdb_id"),
        "episode",
    )
    previous_episode_posters_checked_at = (
        existing_episode["last_tmdb_posters_checked_at"]
        if existing_episode is not None
        else None
    )
    season_posters, season_poster_downloads = (
        poster_storage._download_series_season_posters(
            series_tmdb_id,
            poster_dir=poster_dir,
            poster_size=poster_size,
            fail_on_poster_error=fail_on_poster_error,
        )
    )
    poster_storage._merge_poster_downloads(
        poster_downloads,
        season_poster_downloads,
    )
    parent_poster_downloads = poster_storage._empty_poster_downloads()
    poster_storage._merge_poster_downloads(
        parent_poster_downloads,
        season_poster_downloads,
    )
    series_id = series["id"] if series is not None else None

    if series is None:
        series_draft = builder.build_media_draft_from_tmdb_match({
            "media_type": "series",
            "tmdb_id": series_tmdb_id,
        })
        series_draft.setdefault("metadata", {})[
            "last_tmdb_posters_checked_at"
        ] = None
        series_save_result = _save_catalog_media_draft_with_posters(
            conn,
            series_draft,
            poster_dir=poster_dir,
            poster_size=poster_size,
            max_posters_per_media=max_posters_per_media,
            fail_on_poster_error=fail_on_poster_error,
        )
        poster_storage._merge_poster_downloads(
            poster_downloads,
            series_save_result["poster_downloads"],
        )
        poster_storage._merge_poster_downloads(
            parent_poster_downloads,
            series_save_result["poster_downloads"],
        )
        series_id = series_save_result["media_id"]
        series_created = True

    media_repository.insert_missing_series_season_posters(
        conn,
        series_id,
        season_posters,
    )
    episode_seed_result = _save_series_episode_seeds(
        conn,
        series_tmdb_id,
        poster_dir=poster_dir,
        poster_size=poster_size,
        max_posters_per_media=max_posters_per_media,
        fail_on_poster_error=fail_on_poster_error,
        fetch_episode_imdb_ids=fetch_episode_imdb_ids,
    )
    poster_storage._merge_poster_downloads(
        poster_downloads,
        episode_seed_result["poster_downloads"],
    )

    media_draft.setdefault("metadata", {})[
        "last_tmdb_posters_checked_at"
    ] = None
    original_save_result = _save_single_media_draft_with_posters(
        conn,
        media_draft,
        poster_dir=poster_dir,
        poster_size=poster_size,
        max_posters_per_media=max_posters_per_media,
        fail_on_poster_error=fail_on_poster_error,
    )
    poster_storage._merge_poster_downloads(
        poster_downloads,
        original_save_result["poster_downloads"],
    )
    media_draft["metadata"]["last_tmdb_posters_checked_at"] = (
        managed_checked_at or previous_episode_posters_checked_at
    )

    if managed_checked_at:
        media_repository.update_media_tmdb_posters_checked_at(
            conn,
            original_save_result["media_id"],
            managed_checked_at,
        )

    if poster_storage._poster_downloads_succeeded(parent_poster_downloads):
        media_repository.update_media_tmdb_posters_checked_at(
            conn,
            series_id,
            current_freshness_timestamp(),
        )

    return {
        "media_id": original_save_result["media_id"],
        "poster_downloads": poster_downloads,
        "poster_files_created": (
            original_save_result.get("poster_files_created", [])
            + poster_downloads.get("downloaded", [])
        ),
        "poster_files_to_delete": [],
        "series_completed": True,
        "saved_original_episode": True,
        "series_created": series_created,
        "saved_media_type": "episode",
        "saved_title": media_draft["metadata"].get("title"),
    }


def _save_series_draft_with_episode_context(
    conn,
    media_draft,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
    fetch_episode_imdb_ids=True,
):
    series_tmdb_id = media_draft["metadata"].get("tmdb_id")

    if series_tmdb_id is None:
        raise ValueError("Series draft requires metadata.tmdb_id.")

    existing_series = media_repository.get_media_by_tmdb_id(
        conn,
        series_tmdb_id,
        "series",
    )
    previous_posters_checked_at = (
        existing_series["last_tmdb_posters_checked_at"]
        if existing_series is not None
        else None
    )
    season_posters, season_poster_downloads = (
        poster_storage._download_series_season_posters(
            series_tmdb_id,
            poster_dir=poster_dir,
            poster_size=poster_size,
            fail_on_poster_error=fail_on_poster_error,
        )
    )
    media_draft.setdefault("metadata", {})[
        "last_tmdb_posters_checked_at"
    ] = None
    series_save_result = _save_single_media_draft_with_posters(
        conn,
        media_draft,
        poster_dir=poster_dir,
        poster_size=poster_size,
        max_posters_per_media=max_posters_per_media,
        fail_on_poster_error=fail_on_poster_error,
    )
    poster_downloads = poster_storage._empty_poster_downloads()
    poster_storage._merge_poster_downloads(
        poster_downloads,
        season_poster_downloads,
    )
    poster_storage._merge_poster_downloads(
        poster_downloads,
        series_save_result["poster_downloads"],
    )
    parent_poster_downloads = poster_storage._empty_poster_downloads()
    poster_storage._merge_poster_downloads(
        parent_poster_downloads,
        season_poster_downloads,
    )
    poster_storage._merge_poster_downloads(
        parent_poster_downloads,
        series_save_result["poster_downloads"],
    )
    media_repository.insert_missing_series_season_posters(
        conn,
        series_save_result["media_id"],
        season_posters,
    )

    refresh_snapshot = media_draft.get("_metadata_refresh_snapshot") or {}
    snapshot_episodes = refresh_snapshot.get("regular_episodes")

    if (
        snapshot_episodes is not None
        and refresh_snapshot.get("media_type") == "series"
        and refresh_snapshot.get("tmdb_id") == series_tmdb_id
    ):
        episode_seed_result = _save_series_episode_metadata_list(
            conn,
            snapshot_episodes,
            poster_dir=poster_dir,
            poster_size=poster_size,
            max_posters_per_media=max_posters_per_media,
            fail_on_poster_error=fail_on_poster_error,
        )
    else:
        episode_seed_result = _save_series_episode_seeds(
            conn,
            series_tmdb_id,
            poster_dir=poster_dir,
            poster_size=poster_size,
            max_posters_per_media=max_posters_per_media,
            fail_on_poster_error=fail_on_poster_error,
            fetch_episode_imdb_ids=fetch_episode_imdb_ids,
        )
    poster_storage._merge_poster_downloads(
        poster_downloads,
        episode_seed_result["poster_downloads"],
    )
    _sync_series_episode_watch_history_for_draft(
        conn,
        series_save_result["media_id"],
        media_draft,
    )

    if poster_storage._poster_downloads_succeeded(parent_poster_downloads):
        checked_at = current_freshness_timestamp()
        media_repository.update_media_tmdb_posters_checked_at(
            conn,
            series_save_result["media_id"],
            checked_at,
        )
        media_draft["metadata"]["last_tmdb_posters_checked_at"] = checked_at
    else:
        media_draft["metadata"]["last_tmdb_posters_checked_at"] = (
            previous_posters_checked_at
        )

    return {
        "media_id": series_save_result["media_id"],
        "poster_downloads": poster_downloads,
        "poster_files_created": (
            series_save_result.get("poster_files_created", [])
            + poster_downloads.get("downloaded", [])
        ),
        "poster_files_to_delete": [],
        "series_completed": True,
        "saved_original_episode": True,
        "saved_media_type": "series",
        "saved_title": media_draft["metadata"].get("title"),
        "episode_seed_count": episode_seed_result["saved_count"],
        "episode_seed_skip_count": episode_seed_result["skipped_existing_count"],
    }


def _sync_series_episode_watch_history_for_draft(conn, series_id, media_draft):
    series_view = media_draft.get("series_view") or {}

    if "episode_watch_history" not in series_view:
        return

    media_repository.sync_series_episode_watch_history(
        conn,
        series_id,
        series_view.get("episode_watch_history", []),
    )


def _save_series_episode_seeds(
    conn,
    series_tmdb_id,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
    fetch_episode_imdb_ids=True,
):
    episode_metadata_list = tmdb.get_tmdb_series_episode_metadata_list(
        series_tmdb_id,
        include_episode_imdb_ids=fetch_episode_imdb_ids,
        checked_at=current_freshness_timestamp(),
    )
    return _save_series_episode_metadata_list(
        conn,
        episode_metadata_list,
        poster_dir=poster_dir,
        poster_size=poster_size,
        max_posters_per_media=max_posters_per_media,
        fail_on_poster_error=fail_on_poster_error,
    )


def _save_series_episode_metadata_list(
    conn,
    episode_metadata_list,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
):
    result = {
        "poster_downloads": poster_storage._empty_poster_downloads(),
        "saved_count": 0,
        "skipped_existing_count": 0,
    }

    for episode_metadata in episode_metadata_list:
        existing_episode = media_repository.get_media_by_tmdb_id(
            conn,
            episode_metadata["tmdb_id"],
            "episode",
        )

        if existing_episode is not None:
            result["skipped_existing_count"] += 1
            continue

        episode_draft = _build_seed_episode_draft(episode_metadata)
        episode_save_result = _save_catalog_media_draft_with_posters(
            conn,
            episode_draft,
            poster_dir=poster_dir,
            poster_size=poster_size,
            max_posters_per_media=max_posters_per_media,
            fail_on_poster_error=fail_on_poster_error,
        )
        poster_storage._merge_poster_downloads(
            result["poster_downloads"],
            episode_save_result["poster_downloads"],
        )
        result["saved_count"] += 1

    return result


def _save_single_media_draft_with_posters(
    conn,
    media_draft,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
):
    poster_storage.limit_draft_posters(media_draft, max_posters_per_media)
    managed = media_draft.get(POSTER_MANAGEMENT_KEY) is not None
    created_user_files = []
    poster_downloads = poster_storage._empty_poster_downloads()

    try:
        if managed:
            created_user_files = poster_storage.materialize_user_posters(
                media_draft,
                poster_dir=poster_dir,
            )
        poster_downloads = poster_storage.download_missing_draft_posters(
            media_draft,
            poster_dir=poster_dir,
            poster_size=poster_size,
            fail_on_error=managed or fail_on_poster_error,
        )
        poster_storage._remove_failed_tmdb_poster_references(
            media_draft,
            poster_downloads,
        )
        media_id = media_repository.save_media_draft(conn, media_draft)
    except Exception:
        poster_storage.cleanup_created_poster_files(
            created_user_files + poster_downloads.get("downloaded", []),
            poster_dir=poster_dir,
        )
        raise

    return {
        "media_id": media_id,
        "poster_downloads": poster_downloads,
        "poster_files_created": (
            created_user_files + poster_downloads.get("downloaded", [])
        ),
        "poster_files_to_delete": [],
        "saved_media_type": media_draft["metadata"].get("media_type"),
        "saved_title": media_draft["metadata"].get("title"),
    }


def _save_catalog_media_draft_with_posters(
    conn,
    media_draft,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
    fail_on_poster_error=False,
):
    poster_storage.limit_draft_posters(media_draft, max_posters_per_media)
    managed = media_draft.get(POSTER_MANAGEMENT_KEY) is not None
    created_user_files = []
    poster_downloads = poster_storage._empty_poster_downloads()

    try:
        if managed:
            created_user_files = poster_storage.materialize_user_posters(
                media_draft,
                poster_dir=poster_dir,
            )
        poster_downloads = poster_storage.download_missing_draft_posters(
            media_draft,
            poster_dir=poster_dir,
            poster_size=poster_size,
            fail_on_error=managed or fail_on_poster_error,
        )
        poster_storage._remove_failed_tmdb_poster_references(
            media_draft,
            poster_downloads,
        )
        media_id = media_repository.save_media_catalog_draft(conn, media_draft)
    except Exception:
        poster_storage.cleanup_created_poster_files(
            created_user_files + poster_downloads.get("downloaded", []),
            poster_dir=poster_dir,
        )
        raise

    return {
        "media_id": media_id,
        "poster_downloads": poster_downloads,
        "poster_files_created": (
            created_user_files + poster_downloads.get("downloaded", [])
        ),
        "poster_files_to_delete": [],
        "saved_media_type": media_draft["metadata"].get("media_type"),
        "saved_title": media_draft["metadata"].get("title"),
    }


def _build_seed_episode_draft(metadata):
    return {
        "media_id": None,
        "metadata": metadata,
        "watch_providers": [],
        "posters": [],
    }


def _normalize_managed_episode_posters(media_draft):
    if media_draft.get(POSTER_MANAGEMENT_KEY) is None:
        return
    metadata = media_draft.get("metadata") or {}
    if metadata.get("media_type") != "episode":
        return
    for poster in media_draft.get("posters", []):
        poster["scope"] = "media"
        poster["series_tmdb_id"] = None
        poster["season_num"] = None
