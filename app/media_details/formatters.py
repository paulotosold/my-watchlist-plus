from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.media_user_data.watch_history_formatters import (
    format_date_range,
    parse_date,
)


WATCH_PROVIDER_GROUPS = (
    ("flatrate", "Flatrate"),
    ("buy", "Buy"),
    ("rent", "Rent"),
)


def build_metadata_display_rows(media_draft):
    rows = []
    metadata = media_draft.get("metadata") or {}
    media_type = metadata.get("media_type")
    series_view = media_draft.get("series_view") or {}

    add_imdb_row(rows, metadata.get("imdb_id"))
    add_tmdb_row(rows, metadata)
    add_metadata_row(rows, "Type", format_media_type(media_type))

    if media_type == "episode":
        episode_details = metadata.get("episode_details") or {}
        add_metadata_row(rows, "Series", episode_details.get("series_title"))

    add_metadata_row(rows, "Title", metadata.get("title"))
    add_metadata_row(rows, "Original Title", metadata.get("original_title"))

    if media_type == "episode":
        episode_details = metadata.get("episode_details") or {}
        add_metadata_row(rows, "Episode", episode_details.get("episode_num"))
        add_metadata_row(rows, "Season", episode_details.get("season_num"))

    add_metadata_row(rows, "Production Status", metadata.get("production_status"))

    if media_type == "series":
        summary = series_view.get("summary") or {}
        add_metadata_row(
            rows,
            "First Air Date",
            format_metadata_date(summary.get("first_air_date")),
        )
        add_metadata_row(
            rows,
            "Last Air Date",
            format_metadata_date(summary.get("last_air_date")),
        )
        add_metadata_row(
            rows,
            "Total Runtime",
            format_runtime_minutes(summary.get("total_runtime_min")),
        )
        add_metadata_row(
            rows,
            "Avg. Episode Runtime",
            format_runtime_minutes(summary.get("avg_episode_runtime_min"), approximate=True),
        )
        add_metadata_row(rows, "Season Count", summary.get("season_count"))
        add_metadata_row(rows, "Episode Count", summary.get("episode_count"))
    else:
        add_metadata_row(
            rows,
            "Release Date",
            format_metadata_date(metadata.get("release_date")),
        )
        add_metadata_row(rows, "Runtime", format_runtime_minutes(metadata.get("runtime_min")))

    add_metadata_row(rows, "Genres", format_name_list(metadata.get("genres")))
    add_metadata_row(
        rows,
        "Spoken Languages",
        format_code_or_name_list(metadata.get("spoken_languages"), "name"),
    )
    add_metadata_row(
        rows,
        "Origin Language",
        format_code_or_name(metadata.get("origin_language"), "name"),
    )
    add_metadata_row(
        rows,
        "Production Countries",
        format_code_or_name_list(metadata.get("production_countries"), "name"),
    )
    add_metadata_row(
        rows,
        "Production Companies",
        format_name_list(metadata.get("production_companies")),
    )

    if media_type == "series":
        add_metadata_row(rows, "Creators", format_name_list(metadata.get("creators")))
    else:
        add_metadata_row(rows, "Directors", format_name_list(metadata.get("directors")))

    if media_type != "series":
        add_metadata_row(rows, "Writers", format_people_with_jobs(metadata.get("writers")))

    cast_label = "Main Cast" if media_type == "series" else "Cast"
    add_metadata_row(rows, cast_label, format_name_list(metadata.get("actors")))
    add_metadata_row(
        rows,
        "Last Sync",
        format_watch_provider_checked_at(metadata.get("last_tmdb_metadata_checked_at")),
    )

    return rows


def add_metadata_row(rows, label, value):
    rows.append({"text": f"{label}: {format_empty_metadata_value(value)}"})


def add_imdb_row(rows, imdb_id):
    if is_empty_metadata_value(imdb_id):
        rows.append({"text": "IMDb ID: None"})
        return

    url = f"https://www.imdb.com/title/{imdb_id}"
    rows.append({
        "text": f'IMDb ID: <a href="{url}">{imdb_id} ↗</a>',
        "tooltip": "Open on IMDb",
    })


def add_tmdb_row(rows, metadata):
    tmdb_id = metadata.get("tmdb_id")
    url = build_tmdb_url(metadata)

    if is_empty_metadata_value(tmdb_id) or not url:
        rows.append({"text": "TMDB ID: None"})
        return

    rows.append({
        "text": f'TMDB ID: <a href="{url}">{tmdb_id} ↗</a>',
        "tooltip": "Open on TMDB",
    })


def build_tmdb_url(metadata):
    tmdb_id = metadata.get("tmdb_id")
    media_type = metadata.get("media_type")

    if is_empty_metadata_value(tmdb_id):
        return None

    if media_type == "movie":
        return f"https://www.themoviedb.org/movie/{tmdb_id}"

    if media_type == "series":
        return f"https://www.themoviedb.org/tv/{tmdb_id}"

    if media_type == "episode":
        episode_details = metadata.get("episode_details") or {}
        series_tmdb_id = episode_details.get("series_tmdb_id")
        season_num = episode_details.get("season_num")
        episode_num = episode_details.get("episode_num")

        if (
            is_empty_metadata_value(series_tmdb_id)
            or is_empty_metadata_value(season_num)
            or is_empty_metadata_value(episode_num)
        ):
            return None

        return (
            f"https://www.themoviedb.org/tv/{series_tmdb_id}"
            f"/season/{season_num}/episode/{episode_num}"
        )

    return None


def format_empty_metadata_value(value):
    if is_empty_metadata_value(value):
        return "None"

    return value


def format_runtime_minutes(minutes, approximate=False):
    if minutes in (None, "", 0):
        return None

    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return str(minutes)

    hours, remaining_minutes = divmod(minutes, 60)
    prefix = "~" if approximate else ""

    if hours and remaining_minutes:
        return f"{prefix}{hours}h {remaining_minutes}min"

    if hours:
        return f"{prefix}{hours}h"

    return f"{prefix}{remaining_minutes}min"


def format_metadata_date(value):
    if not value:
        return None

    parsed = parse_date(value)

    if parsed is None:
        return str(value)

    return format_date_range(parsed, parsed)


def format_media_type(media_type):
    if media_type is None:
        return None

    return str(media_type).capitalize()


def format_name_list(items):
    if not items:
        return None

    return ", ".join(
        str(item.get("name") if isinstance(item, dict) else item)
        for item in items
        if item
    )


def format_code_or_name(item, key):
    if not item:
        return None

    if isinstance(item, dict):
        fallback_key = "code" if key == "name" else "name"
        return item.get(key) or item.get(fallback_key)

    return str(item)


def format_code_or_name_list(items, key):
    if not items:
        return None

    values = [
        format_code_or_name(item, key)
        for item in items
    ]
    return ", ".join(value for value in values if value)


def format_people_with_jobs(items):
    if not items:
        return None

    formatted = []

    for item in items:
        if not item:
            continue

        if not isinstance(item, dict):
            formatted.append(str(item))
            continue

        name = item.get("name")

        if not name:
            continue

        if item.get("job"):
            formatted.append(f"{name} ({item['job']})")
        else:
            formatted.append(name)

    return ", ".join(formatted) or None


def group_watch_providers(providers):
    grouped = {access_type: [] for access_type, _ in WATCH_PROVIDER_GROUPS}
    seen = set()

    for provider in providers or []:
        access_type = provider.get("access_type")
        provider_name = provider.get("provider_name")

        if access_type not in grouped or not provider_name:
            continue

        key = (access_type, provider_name)

        if key in seen:
            continue

        seen.add(key)
        grouped[access_type].append(provider_name)

    return grouped


def format_watch_provider_checked_at(checked_at=None):
    media_checked_at = parse_watch_provider_checked_at(checked_at)

    if media_checked_at is not None:
        return format_checked_at_datetime(media_checked_at)

    return None


def format_checked_at_datetime(checked_at):
    local_checked_at = to_local_datetime(checked_at)
    timezone_name = local_checked_at.strftime("%Z")
    timezone_suffix = f" {timezone_name}" if timezone_name else ""

    return f"{local_checked_at.day} {local_checked_at:%b %Y, %H:%M}{timezone_suffix}"


def to_local_datetime(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone()


def parse_watch_provider_checked_at(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        checked_at = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    return checked_at


def get_poster_curation_status(posters):
    if any(poster.get("curation_status") == "pending" for poster in posters or []):
        return "Curation Status: Pending"

    return "Curation Status: Resolved"


def build_tmdb_match_from_metadata(metadata):
    media_type = metadata.get("media_type")
    match = {
        "media_type": media_type,
        "tmdb_id": metadata.get("tmdb_id"),
    }

    if media_type == "episode":
        episode_details = metadata.get("episode_details") or {}
        match.update({
            "series_tmdb_id": episode_details.get("series_tmdb_id"),
            "season_num": episode_details.get("season_num"),
            "episode_num": episode_details.get("episode_num"),
        })

    return match


def is_empty_metadata_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
