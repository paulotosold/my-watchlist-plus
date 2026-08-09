"""TMDB poster discovery, filtering, and CDN URL helpers."""

from urllib.parse import quote, unquote

from app.config import TMDB_LANGUAGE, TMDB_POSTER_SIZE
from .client import get_default_client


TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"


def get_tmdb_movie_posters(tmdb_id, *, client=None):
    return get_tmdb_media_posters(
        {
            "media_type": "movie",
            "tmdb_id": tmdb_id,
        },
        client=client,
    )


def get_tmdb_media_posters(tmdb_id_match, *, client=None):
    tmdb_id_match = _unwrap_resolved_match(
        tmdb_id_match,
        function_name="get_tmdb_media_posters",
    )
    client = _resolve_client(client)
    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        return _get_tmdb_movie_posters(
            tmdb_id_match["tmdb_id"],
            client=client,
        )

    if media_type == "series":
        return _get_tmdb_series_posters(
            tmdb_id_match["tmdb_id"],
            client=client,
        )

    if media_type == "episode":
        return _get_tmdb_episode_posters(
            tmdb_id_match,
            client=client,
        )

    raise ValueError(f"Unsupported media_type: {media_type}")


def get_tmdb_series_primary_season_posters(
    series_tmdb_id,
    *,
    client=None,
):
    client = _resolve_client(client)
    series_details = client.get_json(f"tv/{series_tmdb_id}")
    return _format_primary_season_posters(
        series_details,
        series_tmdb_id,
    )


def build_tmdb_image_url(file_path, size=TMDB_POSTER_SIZE):
    """Build a safe TMDB CDN URL, or return ``None`` for invalid input."""
    normalized_size = str(size or "").strip()

    if not (
        normalized_size == "original"
        or (
            normalized_size.startswith("w")
            and normalized_size[1:].isdigit()
        )
    ):
        return None

    normalized_path = str(file_path or "").strip()

    if not normalized_path or "://" in normalized_path:
        return None

    filename = normalized_path.lstrip("/")
    decoded_filename = unquote(filename)

    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or decoded_filename in {".", ".."}
        or "/" in decoded_filename
        or "\\" in decoded_filename
        or "?" in decoded_filename
        or "#" in decoded_filename
    ):
        return None

    return (
        f"{TMDB_IMAGE_BASE_URL}/{normalized_size}/"
        f"{quote(decoded_filename, safe='-._~')}"
    )


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
            or poster.get("iso_639_1")
            not in {"en", None, original_language}
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


def _format_primary_season_posters(series_details, series_tmdb_id):
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


def _tmdb_image_params(original_language=None):
    include_image_languages = ["en", "null"]

    if (
        original_language
        and original_language not in include_image_languages
    ):
        include_image_languages.append(original_language)

    return {
        "language": TMDB_LANGUAGE,
        "include_image_language": ",".join(include_image_languages),
    }


def _get_tmdb_movie_posters(tmdb_id, *, client=None):
    client = _resolve_client(client)
    movie_details = client.get_json(f"movie/{tmdb_id}")
    original_language = movie_details.get("original_language")
    movie_images = client.get_json(
        f"movie/{tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return _format_tmdb_posters(
        movie_images,
        scope="media",
        original_language=original_language,
    )


def _get_tmdb_series_posters(tmdb_id, *, client=None):
    client = _resolve_client(client)
    series_details = client.get_json(f"tv/{tmdb_id}")
    original_language = series_details.get("original_language")
    series_images = client.get_json(
        f"tv/{tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return _format_tmdb_posters(
        series_images,
        scope="media",
        original_language=original_language,
    )


def _get_tmdb_episode_posters(tmdb_id_match, *, client=None):
    client = _resolve_client(client)
    series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
    season_num = tmdb_id_match.get("season_num")

    if not series_tmdb_id or season_num is None:
        raise ValueError(
            "Episode posters require series_tmdb_id and season_num."
        )

    series_details = client.get_json(f"tv/{series_tmdb_id}")
    original_language = series_details.get("original_language")
    image_params = _tmdb_image_params(original_language)
    season_images = client.get_json(
        f"tv/{series_tmdb_id}/season/{season_num}/images",
        params=image_params,
    )
    series_images = client.get_json(
        f"tv/{series_tmdb_id}/images",
        params=image_params,
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


def _unwrap_resolved_match(tmdb_id_match, *, function_name):
    if tmdb_id_match.get("status"):
        if (
            tmdb_id_match.get("status") != "resolved"
            or not tmdb_id_match.get("match")
        ):
            raise ValueError(
                f"{function_name} requires a resolved TMDB match."
            )

        return tmdb_id_match["match"]

    return tmdb_id_match


def _resolve_client(client):
    return client if client is not None else get_default_client()
