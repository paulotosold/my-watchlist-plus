from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


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

    add_metadata_row(rows, "TMDB ID", metadata.get("tmdb_id"))
    add_imdb_row(rows, metadata.get("imdb_id"))
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
        add_metadata_row(rows, "First Air Date", summary.get("first_air_date"))
        add_metadata_row(rows, "Last Air Date", summary.get("last_air_date"))
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
        add_metadata_row(rows, "Release Date", metadata.get("release_date"))
        add_metadata_row(rows, "Runtime", format_runtime_minutes(metadata.get("runtime_min")))

    add_metadata_row(rows, "Genres", format_name_list(metadata.get("genres")))
    add_metadata_row(
        rows,
        "Spoken Languages",
        format_code_or_name_list(metadata.get("spoken_languages"), "code"),
    )
    add_metadata_row(
        rows,
        "Origin Language",
        format_code_or_name(metadata.get("origin_language"), "code"),
    )
    add_metadata_row(
        rows,
        "Production Countries",
        format_code_or_name_list(metadata.get("production_countries"), "code"),
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
        return item.get(key) or item.get("name")

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


def build_watch_history_display_lines(media_draft):
    metadata = media_draft.get("metadata") or {}

    if metadata.get("media_type") == "series":
        return build_series_watch_history_lines(media_draft)

    return [
        format_watch_history_entry(
            event,
            release_date=metadata.get("release_date"),
        )
        for event in sorted(
            media_draft.get("user_data", {}).get("watch_history", []),
            key=watch_history_sort_key,
        )
    ]


def build_series_watch_history_lines(media_draft):
    metadata = media_draft.get("metadata") or {}
    series_view = media_draft.get("series_view") or {}
    summary = series_view.get("summary") or {}
    release_date = summary.get("first_air_date") or metadata.get("release_date")
    lines = []

    for event in sorted(
        media_draft.get("user_data", {}).get("watch_history", []),
        key=watch_history_sort_key,
    ):
        lines.append({
            "created_at": event.get("created_at"),
            "text": (
                f"{format_watch_history_entry(event, release_date=release_date)}"
                " · no episode info"
            ),
        })

    for group in group_episode_watch_history(
        series_view.get("episode_watch_history", [])
    ):
        representative = group[0]
        date_label = format_watch_history_entry(
            representative,
            release_date=release_date,
        )
        lines.append({
            "created_at": representative.get("created_at"),
            "text": f"{date_label} · {format_episode_ranges(group)}",
        })

    return [
        line["text"]
        for line in sorted(
            lines,
            key=lambda item: item.get("created_at") or "",
        )
    ]


def group_episode_watch_history(rows):
    groups = {}

    for row in rows or []:
        key = (
            row.get("watch_history_id"),
            row.get("date_earliest"),
            row.get("date_latest"),
            row.get("created_at"),
        )
        groups.setdefault(key, []).append(row)

    return [
        sorted(
            group,
            key=lambda item: (
                item.get("season_num") or 0,
                item.get("episode_num") or 0,
            ),
        )
        for _, group in sorted(
            groups.items(),
            key=lambda item: (
                item[0][3] or "",
                item[0][0] or 0,
            ),
        )
    ]


def format_episode_ranges(rows):
    episodes_by_season = {}

    for row in rows:
        season_num = row.get("season_num")
        episode_num = row.get("episode_num")

        if season_num is None or episode_num is None:
            continue

        episodes_by_season.setdefault(season_num, set()).add(episode_num)

    parts = []

    for season_num in sorted(episodes_by_season):
        ranges = compress_int_ranges(sorted(episodes_by_season[season_num]))
        parts.extend(
            f"S{season_num}:E{episode_range}"
            for episode_range in ranges
        )

    return ", ".join(parts) or "episode info"


def compress_int_ranges(values):
    if not values:
        return []

    ranges = []
    start = values[0]
    previous = values[0]

    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue

        ranges.append(format_int_range(start, previous))
        start = previous = value

    ranges.append(format_int_range(start, previous))
    return ranges


def format_int_range(start, end):
    if start == end:
        return str(start)

    return f"{start}-{end}"


def watch_history_sort_key(event):
    return (
        event.get("created_at") or "",
        event.get("id") or event.get("watch_history_id") or 0,
    )


def format_watch_history_entry(event, release_date=None):
    earliest = parse_date(event.get("date_earliest"))
    latest = parse_date(event.get("date_latest"))
    inferred = False

    if earliest is None or latest is None:
        inferred = True
        earliest = earliest or parse_date(release_date) or parse_date(event.get("created_at"))
        latest = latest or parse_date(event.get("created_at")) or earliest

    if earliest is None and latest is None:
        label = "unknown date"
    else:
        if earliest is None:
            earliest = latest

        if latest is None:
            latest = earliest

        if latest < earliest:
            earliest, latest = latest, earliest

        label = format_date_range(earliest, latest)

    if inferred:
        return f"Probably {label}"

    return label


def parse_date(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    value = str(value)

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue

    return None


def format_date_range(earliest, latest):
    if earliest == latest:
        return earliest.strftime("%d %b %Y, %a").lstrip("0")

    if earliest.year == latest.year and earliest.month == latest.month:
        return earliest.strftime("%b %Y")

    if earliest.year == latest.year:
        return str(earliest.year)

    return f"{earliest.year}-{latest.year}"


def is_empty_metadata_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
