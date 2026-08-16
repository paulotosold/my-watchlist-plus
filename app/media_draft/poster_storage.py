"""Download and validate poster files referenced by media drafts."""

from pathlib import Path
from hashlib import sha256
import shutil

import requests

from app.config import TMDB_MAX_POSTERS_PER_MEDIA, TMDB_POSTER_SIZE
from app.paths import MEDIA_POSTERS_DIR
import app.tmdb as tmdb


DEFAULT_POSTER_DIR = MEDIA_POSTERS_DIR


def limit_draft_posters(
    media_draft,
    max_posters_per_media=TMDB_MAX_POSTERS_PER_MEDIA,
):
    explicitly_selected = [
        poster
        for poster in media_draft.get("posters", [])
        if poster.get("curation_status") == "selected"
    ]
    if explicitly_selected:
        media_draft["posters"] = explicitly_selected
        return media_draft

    if max_posters_per_media is None:
        return media_draft

    if max_posters_per_media < 1:
        media_draft["posters"] = []
        return media_draft

    media_draft["posters"] = (
        media_draft.get("posters", [])[:max_posters_per_media]
    )

    return media_draft


def download_missing_draft_posters(
    media_draft,
    poster_dir=DEFAULT_POSTER_DIR,
    poster_size=TMDB_POSTER_SIZE,
    fail_on_error=False,
):
    poster_dir = Path(poster_dir)
    poster_dir.mkdir(parents=True, exist_ok=True)

    results = _empty_poster_downloads()
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
                cleanup_created_poster_files(
                    results["downloaded"],
                    poster_dir=poster_dir,
                )
                raise

    return results


def materialize_user_posters(media_draft, poster_dir=DEFAULT_POSTER_DIR):
    """Copy selected user imports, returning newly created filenames."""
    poster_dir = Path(poster_dir)
    poster_dir.mkdir(parents=True, exist_ok=True)
    created = []

    try:
        for poster in media_draft.get("posters", []):
            if poster.get("source") != "user":
                continue
            filename = _normalize_tmdb_poster_filename(poster.get("filename"))
            source_value = poster.get("_import_path")
            destination = poster_dir / filename

            if destination.is_file() and destination.stat().st_size > 0:
                expected_hash = poster.get("_content_hash")
                if expected_hash and _hash_file(destination) != expected_hash:
                    raise ValueError(f"Poster filename collision: {filename}")
                continue

            if not source_value:
                raise ValueError(f"Imported poster is no longer available: {filename}")
            source = Path(source_value)
            if not source.is_file():
                raise ValueError(f"Imported poster is no longer available: {source}")
            expected_hash = poster.get("_content_hash")
            actual_hash = _hash_file(source)
            if expected_hash and actual_hash != expected_hash:
                raise ValueError(f"Imported poster changed after selection: {source.name}")

            temp_path = destination.with_name(f"{destination.name}.tmp")
            shutil.copy2(source, temp_path)
            temp_path.replace(destination)
            created.append(filename)
    except Exception:
        cleanup_created_poster_files(created, poster_dir=poster_dir)
        raise

    return created


def cleanup_created_poster_files(filenames, poster_dir=DEFAULT_POSTER_DIR):
    poster_dir = Path(poster_dir)
    for filename in filenames or []:
        path = poster_dir / _normalize_tmdb_poster_filename(filename)
        if path.is_file():
            path.unlink()


def delete_unreferenced_poster_files(
    conn,
    filenames,
    poster_dir=DEFAULT_POSTER_DIR,
):
    import app.media_repository as media_repository

    deleted = []
    poster_dir = Path(poster_dir)
    for raw_filename in filenames or []:
        filename = _normalize_tmdb_poster_filename(raw_filename)
        if media_repository.poster_filename_is_referenced(conn, filename):
            continue
        path = poster_dir / filename
        if path.is_file():
            path.unlink()
            deleted.append(filename)
    return deleted


def finalize_managed_poster_draft(media_draft):
    """Remove dialog-only poster state after a successful commit."""
    media_draft.pop("_poster_management", None)
    for poster in media_draft.get("posters", []):
        for key in list(poster):
            if str(key).startswith("_"):
                poster.pop(key, None)


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


def _hash_file(path):
    digest = sha256()
    with Path(path).open("rb") as poster_file:
        for chunk in iter(lambda: poster_file.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_POSTER_DIR",
    "download_missing_draft_posters",
    "download_tmdb_poster",
    "materialize_user_posters",
    "cleanup_created_poster_files",
    "delete_unreferenced_poster_files",
    "finalize_managed_poster_draft",
    "limit_draft_posters",
]
