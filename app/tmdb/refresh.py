"""Build cancellable TMDB metadata refresh snapshots."""

from concurrent.futures import CancelledError

import requests

from app.media_freshness import current_freshness_timestamp
from .client import get_default_client
from .metadata import (
    _format_series_episode_seed_metadata,
    _format_tmdb_episode_metadata,
    _format_tmdb_movie_metadata,
    _format_tmdb_series_metadata,
    _format_tmdb_series_summary,
    _format_spoken_languages,
    _unwrap_resolved_tmdb_match,
)


def _tmdb_get(endpoint, params=None, *, client=None):
    client = client or get_default_client()

    if params is None:
        return client.get_json(endpoint)

    return client.get_json(endpoint, params=params)


SERIES_EPISODE_REFRESH_FIELDS = {
    "tmdb_id",
    "media_type",
    "title",
    "original_title",
    "production_status",
    "release_date",
    "runtime_min",
    "genres",
    "spoken_languages",
    "origin_language",
    "production_countries",
    "production_companies",
    "creators",
    "episode_details",
    "last_tmdb_metadata_checked_at",
}


def get_tmdb_metadata_refresh_snapshot(
    tmdb_id_match,
    should_cancel=None,
    report_progress=None,
    *,
    client=None,
):
    """Fetch a self-contained metadata refresh without changing local state.

    The root metadata is complete. ``regular_episodes`` contains intentionally
    partial episode metadata for a series: per-episode IMDb IDs and credits are
    not fetched, and ``loaded_fields`` identifies the fields that are safe for
    the persistence layer to replace.
    """
    tmdb_id_match = _unwrap_resolved_tmdb_match(
        tmdb_id_match,
        "get_tmdb_metadata_refresh_snapshot",
    )
    media_type = tmdb_id_match.get("media_type")
    tmdb_id = tmdb_id_match.get("tmdb_id")

    if media_type not in {"movie", "series", "episode"}:
        raise ValueError(f"Unsupported media_type: {media_type}")

    if tmdb_id is None:
        raise ValueError("Metadata refresh requires tmdb_id.")

    checked_at = current_freshness_timestamp()
    _raise_if_refresh_cancelled(should_cancel)

    if media_type == "movie":
        metadata = _get_tmdb_movie_refresh_metadata(
            tmdb_id,
            should_cancel,
            report_progress,
            client,
        )
        regular_episodes = None
        series_summary = None
    elif media_type == "series":
        metadata, regular_episodes, series_summary = (
            _get_tmdb_series_refresh_metadata(
                tmdb_id,
                checked_at,
                should_cancel,
                report_progress,
                client,
            )
        )
    else:
        metadata = _get_tmdb_episode_refresh_metadata(
            tmdb_id_match,
            should_cancel,
            report_progress,
            client,
        )
        regular_episodes = None
        series_summary = None

    metadata["last_tmdb_metadata_checked_at"] = checked_at
    _raise_if_refresh_cancelled(should_cancel)
    _report_refresh_progress(report_progress, "Metadata refresh fetched")

    return {
        "media_type": media_type,
        "tmdb_id": tmdb_id,
        "checked_at": checked_at,
        "metadata": metadata,
        "regular_episodes": regular_episodes,
        "series_summary": series_summary,
        "loaded_fields": {
            "metadata": sorted(metadata),
            "regular_episodes": (
                sorted(SERIES_EPISODE_REFRESH_FIELDS)
                if media_type == "series"
                else []
            ),
            "series_summary": (
                sorted(series_summary) if series_summary is not None else []
            ),
        },
    }


def _raise_if_refresh_cancelled(should_cancel):
    if should_cancel is not None and should_cancel():
        raise CancelledError()


def _report_refresh_progress(report_progress, message):
    if report_progress is not None:
        report_progress(message)


def _refresh_get(endpoint, should_cancel, report_progress, message, client):
    _raise_if_refresh_cancelled(should_cancel)
    _report_refresh_progress(report_progress, message)
    if client is None:
        result = _tmdb_get(endpoint)
    else:
        result = _tmdb_get(endpoint, client=client)
    _raise_if_refresh_cancelled(should_cancel)
    return result


def _validate_refresh_identity(payload, expected_tmdb_id, media_label):
    if payload.get("id") != expected_tmdb_id:
        raise ValueError(
            f"TMDB returned a different {media_label} identity: "
            f"expected {expected_tmdb_id}, got {payload.get('id')}."
        )


def _get_tmdb_movie_refresh_metadata(
    tmdb_id,
    should_cancel,
    report_progress,
    client,
):
    movie_details = _refresh_get(
        f"movie/{tmdb_id}",
        should_cancel,
        report_progress,
        "Fetching movie metadata",
        client,
    )
    _validate_refresh_identity(movie_details, tmdb_id, "movie")
    movie_credits = _refresh_get(
        f"movie/{tmdb_id}/credits",
        should_cancel,
        report_progress,
        "Fetching movie credits",
        client,
    )
    return _format_tmdb_movie_metadata(movie_details, movie_credits)


def _get_tmdb_series_refresh_metadata(
    tmdb_id,
    checked_at,
    should_cancel,
    report_progress,
    client,
):
    series_details = _refresh_get(
        f"tv/{tmdb_id}",
        should_cancel,
        report_progress,
        "Fetching series metadata",
        client,
    )
    _validate_refresh_identity(series_details, tmdb_id, "series")
    series_ids = _refresh_get(
        f"tv/{tmdb_id}/external_ids",
        should_cancel,
        report_progress,
        "Fetching series external IDs",
        client,
    )
    series_credits = _refresh_get(
        f"tv/{tmdb_id}/credits",
        should_cancel,
        report_progress,
        "Fetching series credits",
        client,
    )
    spoken_languages = _format_spoken_languages(
        series_details.get("spoken_languages", [])
    )
    episodes = []

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")

        if season_num is None or season_num < 1:
            continue

        if season.get("episode_count") == 0:
            continue

        season_details = _refresh_get(
            f"tv/{tmdb_id}/season/{season_num}",
            should_cancel,
            report_progress,
            f"Fetching season {season_num}",
            client,
        )

        for raw_episode in season_details.get("episodes", []):
            episode = dict(raw_episode)
            episode.setdefault("season_number", season_num)
            episode_metadata = _format_series_episode_seed_metadata(
                series_details=series_details,
                series_ids=series_ids,
                spoken_languages=spoken_languages,
                episode=episode,
                include_episode_imdb_id=False,
                checked_at=checked_at,
                client=client,
            )

            if episode_metadata is not None:
                episodes.append(episode_metadata)

    episodes.sort(
        key=lambda item: (
            item["episode_details"]["season_num"],
            item["episode_details"]["episode_num"],
        )
    )

    return (
        _format_tmdb_series_metadata(
            series_details,
            series_ids,
            series_credits,
        ),
        episodes,
        _format_tmdb_series_summary(series_details),
    )


def _get_tmdb_episode_refresh_metadata(
    tmdb_id_match,
    should_cancel,
    report_progress,
    client,
):
    episode_tmdb_id = tmdb_id_match["tmdb_id"]
    series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
    season_num = tmdb_id_match.get("season_num")
    episode_num = tmdb_id_match.get("episode_num")

    if series_tmdb_id is None:
        raise ValueError("Episode metadata refresh requires series_tmdb_id.")

    series_details = _refresh_get(
        f"tv/{series_tmdb_id}",
        should_cancel,
        report_progress,
        "Fetching parent series metadata",
        client,
    )
    _validate_refresh_identity(series_details, series_tmdb_id, "series")
    series_ids = _refresh_get(
        f"tv/{series_tmdb_id}/external_ids",
        should_cancel,
        report_progress,
        "Fetching parent series external IDs",
        client,
    )

    episode_details = None
    if season_num is not None and episode_num is not None:
        try:
            episode_details = _refresh_get(
                "tv/{series_id}/season/{season_num}/episode/{episode_num}".format(
                    series_id=series_tmdb_id,
                    season_num=season_num,
                    episode_num=episode_num,
                ),
                should_cancel,
                report_progress,
                "Fetching episode metadata",
                client,
            )
        except requests.HTTPError as exc:
            if not _is_tmdb_not_found_error(exc):
                raise

    if (
        episode_details is None
        or episode_details.get("id") != episode_tmdb_id
    ):
        season_num, episode_num = _find_regular_episode_position(
            series_details,
            episode_tmdb_id,
            should_cancel,
            report_progress,
            client,
        )
        episode_details = _refresh_get(
            "tv/{series_id}/season/{season_num}/episode/{episode_num}".format(
                series_id=series_tmdb_id,
                season_num=season_num,
                episode_num=episode_num,
            ),
            should_cancel,
            report_progress,
            "Refetching episode at its current position",
            client,
        )

    _validate_refresh_identity(episode_details, episode_tmdb_id, "episode")
    episode_endpoint = (
        "tv/{series_id}/season/{season_num}/episode/{episode_num}".format(
            series_id=series_tmdb_id,
            season_num=season_num,
            episode_num=episode_num,
        )
    )
    episode_ids = _refresh_get(
        f"{episode_endpoint}/external_ids",
        should_cancel,
        report_progress,
        "Fetching episode external IDs",
        client,
    )
    episode_credits = _refresh_get(
        f"{episode_endpoint}/credits",
        should_cancel,
        report_progress,
        "Fetching episode credits",
        client,
    )

    return _format_tmdb_episode_metadata(
        series_details=series_details,
        series_ids=series_ids,
        episode_details=episode_details,
        episode_ids=episode_ids,
        episode_credits=episode_credits,
        season_num=season_num,
        episode_num=episode_num,
    )


def _is_tmdb_not_found_error(exc):
    response = getattr(exc, "response", None)
    return response is not None and response.status_code == 404


def _find_regular_episode_position(
    series_details,
    episode_tmdb_id,
    should_cancel,
    report_progress,
    client,
):
    series_tmdb_id = series_details["id"]

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")

        if season_num is None or season_num < 1:
            continue

        if season.get("episode_count") == 0:
            continue

        season_details = _refresh_get(
            f"tv/{series_tmdb_id}/season/{season_num}",
            should_cancel,
            report_progress,
            f"Locating episode in season {season_num}",
            client,
        )

        for episode in season_details.get("episodes", []):
            if episode.get("id") != episode_tmdb_id:
                continue

            current_season_num = episode.get("season_number", season_num)
            current_episode_num = episode.get("episode_number")

            if current_season_num < 1 or current_episode_num is None:
                break

            return current_season_num, current_episode_num

    raise ValueError(
        f"TMDB episode {episode_tmdb_id} was not found in the regular "
        f"seasons of series {series_tmdb_id}."
    )
