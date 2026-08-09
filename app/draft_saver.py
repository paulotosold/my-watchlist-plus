from pathlib import Path

import requests

import app.media_draft_builder as media_draft_builder
from app.media_freshness import current_freshness_timestamp
import app.media_repository as media_repository
import app.tmdb as tmdb
from app.config import BASE_DIR, TMDB_MAX_POSTERS_PER_MEDIA, TMDB_POSTER_SIZE


DEFAULT_POSTER_DIR = BASE_DIR / "data" / "media_posters"


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
            media_draft = media_draft_builder.build_media_draft_from_tmdb(imdb_id)
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


def save_existing_media_changes(conn, baseline_draft, media_draft):
    """Persist only user-owned changes for an existing media item.

    Catalog metadata, posters, providers, and series episode materialization are
    deliberately outside this path.  The caller owns the transaction and must
    apply returned database IDs to the live draft only after commit succeeds.
    """
    media_id = media_draft.get("media_id")

    if media_id is None or baseline_draft.get("media_id") != media_id:
        raise ValueError("Existing-media save requires matching media ids.")

    result = media_repository.apply_media_user_changes(
        conn,
        media_id,
        baseline_draft,
        media_draft,
    )
    metadata = media_draft.get("metadata") or {}
    return {
        **result,
        "media_id": media_id,
        "poster_downloads": _empty_poster_downloads(),
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
    episode_details = media_draft["metadata"].get("episode_details") or {}
    series_tmdb_id = episode_details.get("series_tmdb_id")

    if series_tmdb_id is None:
        raise ValueError("Episode draft requires episode_details.series_tmdb_id.")

    poster_downloads = _empty_poster_downloads()
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
        _download_series_season_posters(
            series_tmdb_id,
            poster_dir=poster_dir,
            poster_size=poster_size,
            fail_on_poster_error=fail_on_poster_error,
        )
    )
    _merge_poster_downloads(poster_downloads, season_poster_downloads)
    parent_poster_downloads = _empty_poster_downloads()
    _merge_poster_downloads(
        parent_poster_downloads,
        season_poster_downloads,
    )
    series_id = series["id"] if series is not None else None

    if series is None:
        series_draft = media_draft_builder.build_media_draft_from_tmdb_match({
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
        _merge_poster_downloads(
            poster_downloads,
            series_save_result["poster_downloads"],
        )
        _merge_poster_downloads(
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
    _merge_poster_downloads(
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
    _merge_poster_downloads(
        poster_downloads,
        original_save_result["poster_downloads"],
    )
    media_draft["metadata"]["last_tmdb_posters_checked_at"] = (
        previous_episode_posters_checked_at
    )

    if _poster_downloads_succeeded(parent_poster_downloads):
        media_repository.update_media_tmdb_posters_checked_at(
            conn,
            series_id,
            current_freshness_timestamp(),
        )

    return {
        "media_id": original_save_result["media_id"],
        "poster_downloads": poster_downloads,
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
        _download_series_season_posters(
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
    poster_downloads = _empty_poster_downloads()
    _merge_poster_downloads(poster_downloads, season_poster_downloads)
    _merge_poster_downloads(
        poster_downloads,
        series_save_result["poster_downloads"],
    )
    parent_poster_downloads = _empty_poster_downloads()
    _merge_poster_downloads(
        parent_poster_downloads,
        season_poster_downloads,
    )
    _merge_poster_downloads(
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
    _merge_poster_downloads(
        poster_downloads,
        episode_seed_result["poster_downloads"],
    )
    _sync_series_episode_watch_history_for_draft(
        conn,
        series_save_result["media_id"],
        media_draft,
    )

    if _poster_downloads_succeeded(parent_poster_downloads):
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
        "poster_downloads": _empty_poster_downloads(),
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
        _merge_poster_downloads(
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
    limit_draft_posters(media_draft, max_posters_per_media)

    poster_downloads = download_missing_draft_posters(
        media_draft,
        poster_dir=poster_dir,
        poster_size=poster_size,
        fail_on_error=fail_on_poster_error,
    )
    _remove_failed_tmdb_poster_references(media_draft, poster_downloads)
    media_id = media_repository.save_media_draft(conn, media_draft)

    return {
        "media_id": media_id,
        "poster_downloads": poster_downloads,
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
    limit_draft_posters(media_draft, max_posters_per_media)

    poster_downloads = download_missing_draft_posters(
        media_draft,
        poster_dir=poster_dir,
        poster_size=poster_size,
        fail_on_error=fail_on_poster_error,
    )
    _remove_failed_tmdb_poster_references(media_draft, poster_downloads)
    media_id = media_repository.save_media_catalog_draft(conn, media_draft)

    return {
        "media_id": media_id,
        "poster_downloads": poster_downloads,
        "saved_media_type": media_draft["metadata"].get("media_type"),
        "saved_title": media_draft["metadata"].get("title"),
    }


def limit_draft_posters(media_draft, max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA):
    if max_posters_per_media is None:
        return media_draft

    if max_posters_per_media < 1:
        media_draft["posters"] = []
        return media_draft

    media_draft["posters"] = media_draft.get("posters", [])[:max_posters_per_media]

    return media_draft


def _build_seed_episode_draft(metadata):
    return {
        "media_id": None,
        "metadata": metadata,
        "watch_providers": [],
        "posters": [],
    }


def _empty_poster_downloads():
    return {
        "downloaded": [],
        "skipped": [],
        "failed": [],
    }


def _merge_poster_downloads(target, source):
    for key in ("downloaded", "skipped", "failed"):
        target[key].extend(source.get(key, []))


def _download_series_season_posters(
    series_tmdb_id,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    fail_on_poster_error=False,
):
    season_posters = (
        tmdb.get_tmdb_series_primary_season_posters(series_tmdb_id)
    )
    poster_downloads = download_missing_draft_posters(
        {"posters": season_posters},
        poster_dir=poster_dir,
        poster_size=poster_size,
        fail_on_error=fail_on_poster_error,
    )
    return (
        _without_failed_tmdb_poster_references(
            season_posters,
            poster_downloads,
        ),
        poster_downloads,
    )


def _remove_failed_tmdb_poster_references(media_draft, poster_downloads):
    media_draft["posters"] = _without_failed_tmdb_poster_references(
        media_draft.get("posters", []),
        poster_downloads,
    )


def _without_failed_tmdb_poster_references(posters, poster_downloads):
    failed_filenames = {
        _poster_filename_key(failure.get("filename"))
        for failure in poster_downloads.get("failed", [])
        if failure.get("filename")
    }

    if not failed_filenames:
        return list(posters)

    return [
        poster
        for poster in posters
        if (
            poster.get("source", "tmdb") != "tmdb"
            or _poster_filename_key(poster.get("filename"))
            not in failed_filenames
        )
    ]


def _poster_filename_key(filename):
    return str(filename).lstrip("/") if filename else None


def _poster_downloads_succeeded(poster_downloads):
    return not poster_downloads.get("failed")


def download_missing_draft_posters(
    media_draft,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    fail_on_error=False,
):
    poster_dir = Path(poster_dir)
    poster_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "downloaded": [],
        "skipped": [],
        "failed": [],
    }
    seen = set()

    for raw_filename in _iter_tmdb_poster_filenames(media_draft):
        try:
            filename = _normalize_tmdb_poster_filename(raw_filename)

            if filename in seen:
                continue

            seen.add(filename)

            poster_path = poster_dir / filename

            if poster_path.exists() and poster_path.stat().st_size > 0:
                results["skipped"].append(filename)
                continue

            download_tmdb_poster(
                filename,
                poster_dir=poster_dir,
                poster_size=poster_size,
            )
            results["downloaded"].append(filename)
        except Exception as exc:
            failure = {
                "filename": raw_filename,
                "error": str(exc),
            }
            results["failed"].append(failure)

            if fail_on_error:
                raise

    return results


def download_tmdb_poster(
    filename,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    timeout=30,
):
    filename = _normalize_tmdb_poster_filename(filename)
    poster_dir = Path(poster_dir)
    poster_dir.mkdir(parents=True, exist_ok=True)

    poster_path = poster_dir / filename
    temp_path = poster_path.with_name(f"{poster_path.name}.tmp")
    image_url = tmdb.build_tmdb_image_url(filename, size=poster_size)

    if image_url is None:
        raise ValueError(f"Invalid TMDB poster URL: {filename}")

    try:
        response = requests.get(image_url, stream=True, timeout=timeout)
        response.raise_for_status()

        with temp_path.open("wb") as poster_file:
            for chunk in response.iter_content(chunk_size=128 * 1024):
                if chunk:
                    poster_file.write(chunk)

        temp_path.replace(poster_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()

        raise

    return poster_path


def _iter_tmdb_poster_filenames(media_draft):
    for poster in media_draft.get("posters", []):
        if poster.get("source", "tmdb") != "tmdb":
            continue

        filename = poster.get("filename")

        if filename:
            yield filename


def _normalize_tmdb_poster_filename(filename):
    filename = str(filename).lstrip("/")

    if not filename:
        raise ValueError("Poster filename is empty.")

    if "/" in filename or "\\" in filename:
        raise ValueError(f"Invalid poster filename: {filename}")

    return filename
