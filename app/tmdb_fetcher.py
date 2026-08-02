from concurrent.futures import CancelledError
from datetime import datetime, timezone

import requests

from app.config import (
    TMDB_LANGUAGE,
    TMDB_WATCH_REGION,
    WATCH_PROVIDER_ACCESS_TYPES,
    require_env,
)

TMDB_READ_ACCESS_TOKEN = require_env("TMDB_READ_ACCESS_TOKEN")
#from helpers import format_filename
#from helpers import clear_folder_images_temp

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {TMDB_READ_ACCESS_TOKEN}"
}

TMDB_TITLE_SEARCH_PAGE_LIMIT = 5


def _get_genre_names(genre_codes):
    genres = {
        28: 'Action',
        12: 'Adventure',
        10759: 'Action & Adventure',
        16: 'Animation',
        35: 'Comedy',
        80: 'Crime',
        99: 'Documentary',
        18: 'Drama',
        10751: 'Family',
        14: 'Fantasy',
        36: 'History',
        27: 'Horror',
        10762: 'Kids',
        10402: 'Music',
        9648: 'Mystery',
        10763: 'News',
        10764: 'Reality',
        10749: 'Romance',
        878: 'Science Fiction',
        10765: 'Sci-Fi & Fantasy',
        10766: 'Soap',
        10770: 'TV Movie',
        10767: 'Talk',
        53: 'Thriller',
        10752: 'War',
        10768: 'War & Politics',
        37: 'Western',
    }

    return [genres[code] for code in genre_codes if code in genres]

TMDB_GENRE_SCOPES = {
    28: "movie",
    12: "movie",
    10759: "series",
    16: "movie_series",
    35: "movie_series",
    80: "movie_series",
    99: "movie_series",
    18: "movie_series",
    10751: "movie_series",
    14: "movie",
    36: "movie",
    27: "movie",
    10762: "series",
    10402: "movie",
    9648: "movie_series",
    10763: "series",
    10764: "series",
    10749: "movie",
    878: "movie",
    10765: "series",
    10766: "series",
    10770: "movie",
    10767: "series",
    53: "movie",
    10752: "movie",
    10768: "series",
    37: "movie_series",
}

WRITER_JOBS = {"Writer", "Screenplay", "Teleplay", "Story"}

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


def _tmdb_get(endpoint, params=None):
    url = f"https://api.themoviedb.org/3/{endpoint.lstrip('/')}"
    response = requests.get(
        url,
        headers=headers,
        params=params or {"language": TMDB_LANGUAGE},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _clean_date(value):
    return value or None


def _clean_runtime(value):
    if value is None or value <= 0:
        return None

    return value


def _format_genres(genres, media_type):
    fallback_scope = "series" if media_type == "episode" else media_type

    return [
        {
            "tmdb_id": genre["id"],
            "name": genre["name"],
            "tmdb_scope": TMDB_GENRE_SCOPES.get(genre["id"], fallback_scope),
        }
        for genre in genres
        if genre.get("id") and genre.get("name")
    ]


def _format_spoken_languages(spoken_languages):
    return [
        {
            "code": language["iso_639_1"],
            "name": language.get("english_name") or language.get("name"),
        }
        for language in spoken_languages
        if language.get("iso_639_1")
    ]


def _format_origin_language(language_code, spoken_languages):
    if not language_code:
        return None

    for language in spoken_languages:
        if language["code"] == language_code:
            return language

    return {
        "code": language_code,
        "name": None,
    }


def _format_production_countries(countries):
    return [
        {
            "code": country["iso_3166_1"],
            "name": country["name"],
        }
        for country in countries
        if country.get("iso_3166_1") and country.get("name")
    ]


def _format_production_companies(companies):
    return [
        {
            "tmdb_id": company["id"],
            "name": company["name"],
        }
        for company in companies
        if company.get("id") and company.get("name")
    ]


def _format_people(people):
    formatted_people = []
    seen = set()

    for person in people:
        tmdb_id = person.get("id")
        name = person.get("name")

        if not tmdb_id or not name or tmdb_id in seen:
            continue

        seen.add(tmdb_id)
        formatted_people.append({
            "tmdb_id": tmdb_id,
            "name": name,
        })

    return formatted_people


def _format_crew(crew, jobs, include_job=False):
    formatted_crew = []
    seen = set()

    for person in crew:
        job = person.get("job")
        tmdb_id = person.get("id")
        name = person.get("name")

        if job not in jobs or not tmdb_id or not name:
            continue

        key = (tmdb_id, job if include_job else None)

        if key in seen:
            continue

        seen.add(key)

        formatted_person = {
            "tmdb_id": tmdb_id,
            "name": name,
        }

        if include_job:
            formatted_person["job"] = job

        formatted_crew.append(formatted_person)

    return formatted_crew


def _format_cast(cast):
    formatted_cast = []
    seen = set()

    for person in cast:
        tmdb_id = person.get("id")
        name = person.get("name")
        character = person.get("character")

        if not tmdb_id or not name:
            continue

        key = (tmdb_id, character)

        if key in seen:
            continue

        seen.add(key)
        formatted_cast.append({
            "tmdb_id": tmdb_id,
            "name": name,
            "character": character,
            "cast_order": person.get("order"),
        })

    return formatted_cast


def current_sqlite_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _with_tmdb_metadata_checked_at(metadata):
    metadata["last_tmdb_metadata_checked_at"] = current_sqlite_timestamp()
    metadata.setdefault("last_tmdb_posters_checked_at", None)
    metadata.setdefault("last_tmdb_watch_providers_checked_at", None)
    return metadata


def _format_watch_providers(watch_provider_data, country_code):
    providers_by_region = watch_provider_data.get("results", {}).get(country_code, {})
    formatted_providers = []
    seen = set()

    for access_type in WATCH_PROVIDER_ACCESS_TYPES:
        for provider in providers_by_region.get(access_type, []):
            provider_tmdb_id = provider.get("provider_id")
            provider_name = provider.get("provider_name")

            if not provider_tmdb_id or not provider_name:
                continue

            key = (provider_tmdb_id, country_code, access_type)

            if key in seen:
                continue

            seen.add(key)
            formatted_providers.append({
                "provider_tmdb_id": provider_tmdb_id,
                "provider_name": provider_name,
                "country_code": country_code,
                "access_type": access_type,
            })

    return formatted_providers


def _format_tmdb_posters(
    image_data,
    scope,
    original_language=None,
    series_tmdb_id=None,
    season_num=None,
):
    formatted_posters = []
    seen = set()

    for poster in image_data.get("posters", []):
        file_path = poster.get("file_path")

        if (
            not file_path
            or poster.get("iso_639_1") not in {"en", None, original_language}
            or not 0.64 <= poster.get("aspect_ratio", 0) <= 0.72
            or poster.get("width", 0) < 500
            or poster.get("height", 0) < 750
        ):
            continue

        filename = file_path.removeprefix("/")

        if filename in seen:
            continue

        seen.add(filename)
        formatted_posters.append({
            "scope": scope,
            "filename": filename,
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False,
            "series_tmdb_id": series_tmdb_id,
            "season_num": season_num,
        })

    return formatted_posters


def _tmdb_image_params(original_language=None):
    include_image_languages = ["en", "null"]

    if original_language and original_language not in include_image_languages:
        include_image_languages.append(original_language)

    return {
        "language": TMDB_LANGUAGE,
        "include_image_language": ",".join(include_image_languages),
    }


# -----------------------------------------------------------------------

def find_tmdb_match_by_imdb_id(imdb_id):
    url = f"https://api.themoviedb.org/3/find/{imdb_id.strip()}"
    params = {
        "external_source": "imdb_id",
        "language": TMDB_LANGUAGE,
    }

    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()

    result = response.json()

    candidates = []

    for movie in result.get("movie_results", []):
        candidates.append({
            "media_type": "movie",
            "tmdb_id": movie["id"],
            "title": movie.get("title"),
            "release_date": movie.get("release_date"),
        })

    for series in result.get("tv_results", []):
        candidates.append({
            "media_type": "series",
            "tmdb_id": series["id"],
            "title": series.get("name"),
            "release_date": series.get("first_air_date"),
        })

    for episode in result.get("tv_episode_results", []):
        candidates.append({
            "media_type": "episode",
            "tmdb_id": episode["id"],
            "title": episode.get("name"),
            "release_date": episode.get("air_date"),
            "series_tmdb_id": episode.get("show_id"),
            "season_num": episode.get("season_number"),
            "episode_num": episode.get("episode_number"),
        })

    if len(candidates) == 1:
        return {
            "status": "resolved",
            "match": candidates[0],
        }

    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "match": None,
            "reason": "IMDb ID matched multiple TMDB media categories.",
            "candidates": candidates,
        }

    return {
        "status": "not_found",
        "match": None,
        "reason": "IMDb ID did not match any TMDB movie, series, or episode.",
    }


def search_tmdb_title_candidates(
    query,
    *,
    language=TMDB_LANGUAGE,
):
    """Return up to five organic TMDB result pages for movies and series."""
    query = (query or "").strip()

    if not query:
        return []

    movies = _search_tmdb_title_pages(
        "search/movie",
        query,
        language,
    )
    series = _search_tmdb_title_pages(
        "search/tv",
        query,
        language,
    )

    movie_candidates = [
        _format_tmdb_title_candidate(result, "movie")
        for result in movies
        if result.get("id") is not None
    ]
    series_candidates = [
        _format_tmdb_title_candidate(result, "series")
        for result in series
        if result.get("id") is not None
    ]
    return [*movie_candidates, *series_candidates]


def _search_tmdb_title_pages(endpoint, query, language):
    first_page = _tmdb_get(endpoint, params={
        "query": query,
        "language": language,
        "page": 1,
    })
    results = list(first_page.get("results") or [])
    total_pages = first_page.get("total_pages") or 0

    try:
        total_pages = int(total_pages)
    except (TypeError, ValueError):
        total_pages = 0

    last_page = min(max(total_pages, 1), TMDB_TITLE_SEARCH_PAGE_LIMIT)

    for page in range(2, last_page + 1):
        response = _tmdb_get(endpoint, params={
            "query": query,
            "language": language,
            "page": page,
        })
        results.extend(response.get("results") or [])

    return results


def _format_tmdb_title_candidate(result, media_type):
    if media_type == "movie":
        title = result.get("title")
        original_title = result.get("original_title")
        release_date = result.get("release_date")
    else:
        title = result.get("name")
        original_title = result.get("original_name")
        release_date = result.get("first_air_date")

    return {
        "source": "tmdb",
        "media_id": None,
        "media_type": media_type,
        "tmdb_id": result["id"],
        "imdb_id": None,
        "title": title,
        "original_title": original_title,
        "release_date": release_date,
        "poster_path": result.get("poster_path"),
    }

# -----------------------------------------------------------------------

def get_tmdb_movie_metadata(tmdb_id):
    return _with_tmdb_metadata_checked_at(_get_tmdb_movie_metadata(tmdb_id))


def get_tmdb_media_metadata(tmdb_id_match):
    if tmdb_id_match.get("status"):
        if tmdb_id_match.get("status") != "resolved" or not tmdb_id_match.get("match"):
            raise ValueError(
                "get_tmdb_media_metadata requires a resolved TMDB match."
            )

        tmdb_id_match = tmdb_id_match["match"]

    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        metadata = _get_tmdb_movie_metadata(tmdb_id_match["tmdb_id"])

    elif media_type == "series":
        metadata = _get_tmdb_series_metadata(tmdb_id_match["tmdb_id"])

    elif media_type == "episode":
        metadata = _get_tmdb_episode_metadata(tmdb_id_match)

    else:
        raise ValueError(f"Unsupported media_type: {media_type}")

    return _with_tmdb_metadata_checked_at(metadata)


def get_tmdb_metadata_refresh_snapshot(
    tmdb_id_match,
    should_cancel=None,
    report_progress=None,
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

    checked_at = current_sqlite_timestamp()
    _raise_if_refresh_cancelled(should_cancel)

    if media_type == "movie":
        metadata = _get_tmdb_movie_refresh_metadata(
            tmdb_id,
            should_cancel,
            report_progress,
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
            )
        )
    else:
        metadata = _get_tmdb_episode_refresh_metadata(
            tmdb_id_match,
            should_cancel,
            report_progress,
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


def _unwrap_resolved_tmdb_match(tmdb_id_match, caller_name):
    if not isinstance(tmdb_id_match, dict):
        raise ValueError(f"{caller_name} requires a TMDB match.")

    if tmdb_id_match.get("status"):
        if (
            tmdb_id_match.get("status") != "resolved"
            or not tmdb_id_match.get("match")
        ):
            raise ValueError(f"{caller_name} requires a resolved TMDB match.")

        return tmdb_id_match["match"]

    return tmdb_id_match


def _raise_if_refresh_cancelled(should_cancel):
    if should_cancel is not None and should_cancel():
        raise CancelledError()


def _report_refresh_progress(report_progress, message):
    if report_progress is not None:
        report_progress(message)


def _refresh_get(endpoint, should_cancel, report_progress, message):
    _raise_if_refresh_cancelled(should_cancel)
    _report_refresh_progress(report_progress, message)
    result = _tmdb_get(endpoint)
    _raise_if_refresh_cancelled(should_cancel)
    return result


def _set_metadata_checked_at(metadata, checked_at):
    metadata["last_tmdb_metadata_checked_at"] = checked_at
    metadata.setdefault("last_tmdb_posters_checked_at", None)
    metadata.setdefault("last_tmdb_watch_providers_checked_at", None)
    return metadata


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
):
    movie_details = _refresh_get(
        f"movie/{tmdb_id}",
        should_cancel,
        report_progress,
        "Fetching movie metadata",
    )
    _validate_refresh_identity(movie_details, tmdb_id, "movie")
    movie_credits = _refresh_get(
        f"movie/{tmdb_id}/credits",
        should_cancel,
        report_progress,
        "Fetching movie credits",
    )
    return _format_tmdb_movie_metadata(movie_details, movie_credits)


def _get_tmdb_series_refresh_metadata(
    tmdb_id,
    checked_at,
    should_cancel,
    report_progress,
):
    series_details = _refresh_get(
        f"tv/{tmdb_id}",
        should_cancel,
        report_progress,
        "Fetching series metadata",
    )
    _validate_refresh_identity(series_details, tmdb_id, "series")
    series_ids = _refresh_get(
        f"tv/{tmdb_id}/external_ids",
        should_cancel,
        report_progress,
        "Fetching series external IDs",
    )
    series_credits = _refresh_get(
        f"tv/{tmdb_id}/credits",
        should_cancel,
        report_progress,
        "Fetching series credits",
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
    )
    _validate_refresh_identity(series_details, series_tmdb_id, "series")
    series_ids = _refresh_get(
        f"tv/{series_tmdb_id}/external_ids",
        should_cancel,
        report_progress,
        "Fetching parent series external IDs",
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
    )
    episode_credits = _refresh_get(
        f"{episode_endpoint}/credits",
        should_cancel,
        report_progress,
        "Fetching episode credits",
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


def get_tmdb_media_series_view(tmdb_id_match):
    if tmdb_id_match.get("status"):
        if tmdb_id_match.get("status") != "resolved" or not tmdb_id_match.get("match"):
            raise ValueError(
                "get_tmdb_media_series_view requires a resolved TMDB match."
            )

        tmdb_id_match = tmdb_id_match["match"]

    if tmdb_id_match["media_type"] != "series":
        return None

    series_tmdb_id = tmdb_id_match["tmdb_id"]
    series_details = _tmdb_get(f"tv/{series_tmdb_id}")

    return {
        "summary": _format_tmdb_series_summary(series_details),
        "episodes": _format_tmdb_series_episodes(series_tmdb_id),
        "episode_watch_history": [],
    }


def _format_tmdb_series_episodes(series_tmdb_id):
    return [
        {
            "series_id": None,
            "episode_id": None,
            "tmdb_id": match.get("tmdb_id"),
            "season_num": match.get("season_num"),
            "episode_num": match.get("episode_num"),
            "title": match.get("title"),
            "release_date": _clean_date(match.get("release_date")),
        }
        for match in get_tmdb_series_episode_matches(series_tmdb_id)
    ]


def _format_tmdb_series_summary(series_details):
    return {
        "season_count": series_details.get("number_of_seasons"),
        "episode_count": series_details.get("number_of_episodes"),
        "first_air_date": _clean_date(series_details.get("first_air_date")),
        "last_air_date": _clean_date(series_details.get("last_air_date")),
        "total_runtime_min": None,
        "avg_episode_runtime_min": None,
    }


def _get_tmdb_movie_metadata(tmdb_id):
    movie_details = _tmdb_get(f"movie/{tmdb_id}")
    movie_credits = _tmdb_get(f"movie/{tmdb_id}/credits")

    return _format_tmdb_movie_metadata(movie_details, movie_credits)


def _format_tmdb_movie_metadata(movie_details, movie_credits):
    spoken_languages = _format_spoken_languages(
        movie_details.get("spoken_languages", [])
    )

    return {
        "tmdb_id": movie_details["id"],
        "imdb_id": movie_details.get("imdb_id"),
        "media_type": "movie",
        "title": movie_details["title"],
        "original_title": movie_details["original_title"],
        "production_status": movie_details.get("status"),
        "release_date": _clean_date(movie_details.get("release_date")),
        "runtime_min": _clean_runtime(movie_details.get("runtime")),

        "genres": _format_genres(movie_details.get("genres", []), "movie"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            movie_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            movie_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            movie_details.get("production_companies", [])
        ),
        "directors": _format_crew(movie_credits.get("crew", []), {"Director"}),
        "creators": [],
        "writers": _format_crew(
            movie_credits.get("crew", []),
            WRITER_JOBS,
            include_job=True,
        ),
        "actors": _format_cast(movie_credits.get("cast", [])),

        "episode_details": None,
    }


def _get_tmdb_series_metadata(tmdb_id):
    series_details = _tmdb_get(f"tv/{tmdb_id}")
    series_ids = _tmdb_get(f"tv/{tmdb_id}/external_ids")
    series_credits = _tmdb_get(f"tv/{tmdb_id}/credits")

    return _format_tmdb_series_metadata(
        series_details,
        series_ids,
        series_credits,
    )


def _format_tmdb_series_metadata(
    series_details,
    series_ids,
    series_credits,
):
    spoken_languages = _format_spoken_languages(
        series_details.get("spoken_languages", [])
    )

    return {
        "tmdb_id": series_details["id"],
        "imdb_id": series_ids.get("imdb_id"),
        "media_type": "series",
        "title": series_details["name"],
        "original_title": series_details["original_name"],
        "production_status": series_details.get("status"),
        "release_date": _clean_date(series_details.get("first_air_date")),
        "runtime_min": None,

        "genres": _format_genres(series_details.get("genres", []), "series"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            series_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            series_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            series_details.get("production_companies", [])
        ),
        "directors": _format_crew(series_credits.get("crew", []), {"Director"}),
        "creators": _format_people(series_details.get("created_by", [])),
        "writers": _format_crew(
            series_credits.get("crew", []),
            WRITER_JOBS,
            include_job=True,
        ),
        "actors": _format_cast(series_credits.get("cast", [])),

        "episode_details": None,
    }


def _get_tmdb_episode_metadata(tmdb_id_match):
    series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
    season_num = tmdb_id_match.get("season_num")
    episode_num = tmdb_id_match.get("episode_num")

    if not series_tmdb_id or season_num is None or episode_num is None:
        raise ValueError(
            "Episode TMDB metadata requires series_tmdb_id, season_num, "
            "and episode_num."
        )

    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    series_ids = _tmdb_get(f"tv/{series_tmdb_id}/external_ids")
    episode_details = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}"
    )
    episode_ids = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}/external_ids"
    )
    episode_credits = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}/credits"
    )

    return _set_metadata_checked_at(
        _format_tmdb_episode_metadata(
            series_details=series_details,
            series_ids=series_ids,
            episode_details=episode_details,
            episode_ids=episode_ids,
            episode_credits=episode_credits,
            season_num=season_num,
            episode_num=episode_num,
        ),
        current_sqlite_timestamp(),
    )


def _format_tmdb_episode_metadata(
    series_details,
    series_ids,
    episode_details,
    episode_ids,
    episode_credits,
    season_num,
    episode_num,
):
    spoken_languages = _format_spoken_languages(
        series_details.get("spoken_languages", [])
    )
    episode_cast = (
        episode_credits.get("cast", [])
        + episode_credits.get("guest_stars", [])
    )

    return {
        "tmdb_id": episode_details["id"],
        "imdb_id": episode_ids.get("imdb_id"),
        "media_type": "episode",
        "title": episode_details.get("name"),
        "original_title": episode_details.get("name"),
        "production_status": series_details.get("status"),
        "release_date": _clean_date(episode_details.get("air_date")),
        "runtime_min": _clean_runtime(episode_details.get("runtime")),

        "genres": _format_genres(series_details.get("genres", []), "series"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            series_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            series_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            series_details.get("production_companies", [])
        ),
        "directors": _format_crew(episode_credits.get("crew", []), {"Director"}),
        "creators": _format_people(series_details.get("created_by", [])),
        "writers": _format_crew(
            episode_credits.get("crew", []),
            WRITER_JOBS,
            include_job=True,
        ),
        "actors": _format_cast(episode_cast),

        "episode_details": {
            "series_tmdb_id": series_details["id"],
            "series_imdb_id": series_ids.get("imdb_id"),
            "series_title": series_details.get("name"),
            "season_num": season_num,
            "episode_num": episode_num,
        },
    }


def get_tmdb_movie_watch_providers(tmdb_id, country_code=TMDB_WATCH_REGION):
    return get_tmdb_media_watch_providers({
        "media_type": "movie",
        "tmdb_id": tmdb_id,
    }, country_code=country_code)


def get_tmdb_media_watch_providers(tmdb_id_match, country_code=TMDB_WATCH_REGION):
    if tmdb_id_match.get("status"):
        if tmdb_id_match.get("status") != "resolved" or not tmdb_id_match.get("match"):
            raise ValueError(
                "get_tmdb_media_watch_providers requires a resolved TMDB match."
            )

        tmdb_id_match = tmdb_id_match["match"]

    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        watch_provider_data = _tmdb_get(
            f"movie/{tmdb_id_match['tmdb_id']}/watch/providers"
        )

    elif media_type == "series":
        watch_provider_data = _tmdb_get(
            f"tv/{tmdb_id_match['tmdb_id']}/watch/providers"
        )

    elif media_type == "episode":
        series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
        season_num = tmdb_id_match.get("season_num")

        if not series_tmdb_id or season_num is None:
            raise ValueError(
                "Episode watch providers require series_tmdb_id and season_num."
            )

        watch_provider_data = _tmdb_get(
            f"tv/{series_tmdb_id}/season/{season_num}/watch/providers"
        )

    else:
        raise ValueError(f"Unsupported media_type: {media_type}")

    return _format_watch_providers(
        watch_provider_data,
        country_code,
    )

def get_tmdb_movie_posters(tmdb_id):
    return get_tmdb_media_posters({
        "media_type": "movie",
        "tmdb_id": tmdb_id,
    })


def get_tmdb_media_posters(tmdb_id_match):
    if tmdb_id_match.get("status"):
        if tmdb_id_match.get("status") != "resolved" or not tmdb_id_match.get("match"):
            raise ValueError(
                "get_tmdb_media_posters requires a resolved TMDB match."
            )

        tmdb_id_match = tmdb_id_match["match"]

    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        return _get_tmdb_movie_posters(tmdb_id_match["tmdb_id"])

    if media_type == "series":
        return _get_tmdb_series_posters(tmdb_id_match["tmdb_id"])

    if media_type == "episode":
        return _get_tmdb_episode_posters(tmdb_id_match)

    raise ValueError(f"Unsupported media_type: {media_type}")


def get_tmdb_series_primary_season_posters(series_tmdb_id):
    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    season_posters = []
    seen_season_nums = set()

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")
        poster_path = season.get("poster_path")

        if (
            season_num is None
            or season_num < 1
            or not poster_path
            or season_num in seen_season_nums
        ):
            continue

        seen_season_nums.add(season_num)
        season_posters.append({
            "scope": "season",
            "filename": poster_path.removeprefix("/"),
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False,
            "series_tmdb_id": series_tmdb_id,
            "season_num": season_num,
        })

    return sorted(
        season_posters,
        key=lambda poster: poster["season_num"],
    )


def get_tmdb_media_user_data(tmdb_id_match=None):
    return {
        "watch_state": "to_watch",
        "impression": None,
        "is_collection_pick": None,
        "watch_history": [],
        "notes": [],
        "lists": [],
    }


def get_tmdb_series_episode_matches(series_tmdb_id):
    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    episode_matches = []

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")

        if season_num is None or season_num < 1:
            continue

        if season.get("episode_count") == 0:
            continue

        season_details = _tmdb_get(
            f"tv/{series_tmdb_id}/season/{season_num}"
        )

        for episode in season_details.get("episodes", []):
            episode_num = episode.get("episode_number")
            episode_tmdb_id = episode.get("id")

            if episode_num is None or episode_tmdb_id is None:
                continue

            episode_matches.append({
                "media_type": "episode",
                "tmdb_id": episode_tmdb_id,
                "title": episode.get("name"),
                "release_date": episode.get("air_date"),
                "series_tmdb_id": series_tmdb_id,
                "season_num": season_num,
                "episode_num": episode_num,
            })

    return sorted(
        episode_matches,
        key=lambda match: (match["season_num"], match["episode_num"]),
    )


def get_tmdb_series_episode_metadata_list(
    series_tmdb_id,
    include_episode_imdb_ids=True,
):
    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    series_ids = _tmdb_get(f"tv/{series_tmdb_id}/external_ids")

    spoken_languages = _format_spoken_languages(
        series_details.get("spoken_languages", [])
    )
    episode_metadata_list = []

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")

        if season_num is None or season_num < 1:
            continue

        if season.get("episode_count") == 0:
            continue

        season_details = _tmdb_get(
            f"tv/{series_tmdb_id}/season/{season_num}"
        )

        for episode in season_details.get("episodes", []):
            episode_metadata = _format_series_episode_seed_metadata(
                series_details=series_details,
                series_ids=series_ids,
                spoken_languages=spoken_languages,
                episode=episode,
                include_episode_imdb_id=include_episode_imdb_ids,
            )

            if episode_metadata is not None:
                episode_metadata_list.append(episode_metadata)

    return sorted(
        episode_metadata_list,
        key=lambda metadata: (
            metadata["episode_details"]["season_num"],
            metadata["episode_details"]["episode_num"],
        ),
    )


def _format_series_episode_seed_metadata(
    series_details,
    series_ids,
    spoken_languages,
    episode,
    include_episode_imdb_id,
    checked_at=None,
):
    episode_tmdb_id = episode.get("id")
    season_num = episode.get("season_number")
    episode_num = episode.get("episode_number")

    if episode_tmdb_id is None or season_num is None or episode_num is None:
        return None

    title = episode.get("name") or f"Episode {episode_num}"
    imdb_id = None

    if include_episode_imdb_id:
        episode_ids = _tmdb_get(
            "tv/{series_tmdb_id}/season/{season_num}/episode/"
            "{episode_num}/external_ids".format(
                series_tmdb_id=series_details["id"],
                season_num=season_num,
                episode_num=episode_num,
            )
        )
        imdb_id = episode_ids.get("imdb_id")

    return {
        "tmdb_id": episode_tmdb_id,
        "imdb_id": imdb_id,
        "media_type": "episode",
        "title": title,
        "original_title": title,
        "production_status": series_details.get("status"),
        "release_date": _clean_date(episode.get("air_date")),
        "runtime_min": _clean_runtime(episode.get("runtime")),

        "genres": _format_genres(series_details.get("genres", []), "series"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            series_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            series_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            series_details.get("production_companies", [])
        ),
        "directors": [],
        "creators": _format_people(series_details.get("created_by", [])),
        "writers": [],
        "actors": [],

        "episode_details": {
            "series_tmdb_id": series_details["id"],
            "series_imdb_id": series_ids.get("imdb_id"),
            "series_title": series_details.get("name"),
            "season_num": season_num,
            "episode_num": episode_num,
        },
        "last_tmdb_metadata_checked_at": (
            checked_at or current_sqlite_timestamp()
        ),
        "last_tmdb_posters_checked_at": None,
        "last_tmdb_watch_providers_checked_at": None,
    }


def _get_tmdb_movie_posters(tmdb_id):
    movie_details = _tmdb_get(f"movie/{tmdb_id}")
    original_language = movie_details.get("original_language")
    movie_images = _tmdb_get(
        f"movie/{tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return _format_tmdb_posters(
        movie_images,
        scope="media",
        original_language=original_language,
    )


def _get_tmdb_series_posters(tmdb_id):
    series_details = _tmdb_get(f"tv/{tmdb_id}")
    original_language = series_details.get("original_language")
    series_images = _tmdb_get(
        f"tv/{tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return _format_tmdb_posters(
        series_images,
        scope="media",
        original_language=original_language,
    )


def _get_tmdb_episode_posters(tmdb_id_match):
    series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
    season_num = tmdb_id_match.get("season_num")

    if not series_tmdb_id or season_num is None:
        raise ValueError(
            "Episode posters require series_tmdb_id and season_num."
        )

    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    original_language = series_details.get("original_language")
    season_images = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/images",
        params=_tmdb_image_params(original_language),
    )
    series_images = _tmdb_get(
        f"tv/{series_tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return (
        _format_tmdb_posters(
            season_images,
            scope="season",
            original_language=original_language,
            series_tmdb_id=series_tmdb_id,
            season_num=season_num,
        )
        + _format_tmdb_posters(
            series_images,
            scope="series",
            original_language=original_language,
            series_tmdb_id=series_tmdb_id,
            season_num=None,
        )
    )




def get_tmdb_infos(tmdb_id, media_type):
    if media_type == "episode":
        raise ValueError(
            "Episode metadata requires a resolved TMDB match with "
            "series_tmdb_id, season_num, and episode_num."
        )

    return get_tmdb_media_metadata({
        "media_type": media_type,
        "tmdb_id": tmdb_id,
    })
