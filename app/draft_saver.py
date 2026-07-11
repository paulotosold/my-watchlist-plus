from pathlib import Path

import requests

import app.media_draft_builder as media_draft_builder
import app.media_repository as media_repository
import app.tmdb_fetcher as tmdb_fetcher
from app.config import BASE_DIR, TMDB_MAX_POSTERS_PER_MEDIA, TMDB_POSTER_SIZE


TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
DEFAULT_POSTER_DIR = BASE_DIR / "data" / "media_posters"
SERIES_COMPLETION_SKIP_STATES = {"dropped", "not_interested"}


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

    original_watch_state = (
        media_draft.get("user_data", {}).get("watch_state") or "to_watch"
    )
    poster_downloads = _empty_poster_downloads()
    series_completed = False
    series_created = False

    series = media_repository.get_media_by_tmdb_id(
        conn,
        series_tmdb_id,
        "series",
    )

    if series is None:
        series_draft = media_draft_builder.build_media_draft_from_tmdb_match({
            "media_type": "series",
            "tmdb_id": series_tmdb_id,
        })
        series_draft["user_data"]["watch_state"] = (
            original_watch_state
            if original_watch_state in SERIES_COMPLETION_SKIP_STATES
            else "watching"
        )
        series_save_result = _save_single_media_draft_with_posters(
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
        series = media_repository.get_media_by_tmdb_id(
            conn,
            series_tmdb_id,
            "series",
        )
        series_created = True

    if original_watch_state in SERIES_COMPLETION_SKIP_STATES:
        return {
            "media_id": series["id"],
            "poster_downloads": poster_downloads,
            "series_completed": False,
            "saved_original_episode": False,
            "series_created": series_created,
            "saved_media_type": "series",
            "saved_title": series["title"],
        }

    if series_created:
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
        series_completed = True

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

    return {
        "media_id": original_save_result["media_id"],
        "poster_downloads": poster_downloads,
        "series_completed": series_completed,
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

    watch_state = media_draft.get("user_data", {}).get("watch_state") or "to_watch"
    series_save_result = _save_single_media_draft_with_posters(
        conn,
        media_draft,
        poster_dir=poster_dir,
        poster_size=poster_size,
        max_posters_per_media=max_posters_per_media,
        fail_on_poster_error=fail_on_poster_error,
    )
    poster_downloads = series_save_result["poster_downloads"]

    if (
        watch_state in SERIES_COMPLETION_SKIP_STATES
        and not _draft_has_series_episode_watch_history(media_draft)
    ):
        _sync_series_episode_watch_history_for_draft(
            conn,
            series_save_result["media_id"],
            media_draft,
        )
        return {
            "media_id": series_save_result["media_id"],
            "poster_downloads": poster_downloads,
            "series_completed": False,
            "saved_original_episode": True,
            "saved_media_type": "series",
            "saved_title": media_draft["metadata"].get("title"),
            "episode_seed_count": 0,
            "episode_seed_skip_count": 0,
        }

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


def _draft_has_series_episode_watch_history(media_draft):
    return bool(
        (media_draft.get("series_view") or {}).get("episode_watch_history")
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
    episode_metadata_list = tmdb_fetcher.get_tmdb_series_episode_metadata_list(
        series_tmdb_id,
        include_episode_imdb_ids=fetch_episode_imdb_ids,
    )
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
        episode_draft["user_data"]["watch_state"] = "to_watch"
        episode_save_result = _save_single_media_draft_with_posters(
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
    media_id = media_repository.save_media_draft(conn, media_draft)

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
        "user_data": {
            "watch_state": "to_watch",
            "impression": None,
            "is_collection_pick": None,
            "watch_history": [],
            "notes": [],
            "lists": [],
        },
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
    image_url = f"{TMDB_IMAGE_BASE_URL}/{poster_size}/{filename}"

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
