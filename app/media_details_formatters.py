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


def build_watch_history_display_entries(media_draft):
    metadata = media_draft.get("metadata") or {}
    release_date = metadata.get("release_date")

    if metadata.get("media_type") == "series":
        return build_series_watch_history_entries(media_draft)

    entries = [
        build_media_watch_history_entry(
            event,
            release_date=release_date,
            index=index,
        )
        for index, event in enumerate(
            media_draft.get("user_data", {}).get("watch_history", [])
        )
    ]

    return sort_watch_history_entries(entries, release_date)


def build_watch_history_display_lines(media_draft):
    return [
        entry["text"]
        for entry in build_watch_history_display_entries(media_draft)
    ]


def build_series_watch_history_entries(media_draft):
    metadata = media_draft.get("metadata") or {}
    series_view = media_draft.get("series_view") or {}
    summary = series_view.get("summary") or {}
    release_date = summary.get("first_air_date") or metadata.get("release_date")
    entries = []

    for index, event in enumerate(
        media_draft.get("user_data", {}).get("watch_history", [])
    ):
        entries.append(
            build_media_watch_history_entry(
                event,
                release_date=release_date,
                index=index,
                text_suffix=" · no episode info",
            )
        )

    for group in group_episode_watch_history(
        series_view.get("episode_watch_history", [])
    ):
        entries.append(build_episode_group_watch_history_entry(group, release_date))

    return sort_watch_history_entries(entries, release_date)


def build_series_watch_history_lines(media_draft):
    return [
        entry["text"]
        for entry in build_series_watch_history_entries(media_draft)
    ]


def build_media_watch_history_entry(
    event,
    release_date=None,
    index=None,
    text_suffix="",
):
    text = format_watch_history_entry(event, release_date=release_date)

    return {
        "kind": "media_event",
        "text": f"{text}{text_suffix}",
        "date_earliest": event.get("date_earliest"),
        "date_latest": event.get("date_latest"),
        "created_at": event.get("created_at"),
        "watch_history_id": event.get("id") or event.get("watch_history_id"),
        "watch_history_index": index,
        "watch_history": dict(event),
    }


def build_episode_group_watch_history_entry(group, release_date=None):
    representative = group[0]
    date_label = format_watch_history_entry(
        representative,
        release_date=release_date,
    )

    return {
        "kind": "episode_group",
        "text": f"{date_label} · {format_episode_ranges(group)}",
        "date_earliest": representative.get("date_earliest"),
        "date_latest": representative.get("date_latest"),
        "created_at": earliest_created_at(group),
        "watch_history_ids": [
            row.get("watch_history_id")
            for row in group
            if row.get("watch_history_id") is not None
        ],
        "draft_ids": [
            row.get("draft_id")
            for row in group
            if row.get("draft_id") is not None
        ],
        "episodes": [
            {
                "series_id": row.get("series_id"),
                "episode_id": row.get("episode_id"),
                "tmdb_id": row.get("tmdb_id"),
                "watch_history_id": row.get("watch_history_id"),
                "draft_id": row.get("draft_id"),
                "season_num": row.get("season_num"),
                "episode_num": row.get("episode_num"),
                "created_at": row.get("created_at"),
            }
            for row in group
        ],
    }


def earliest_created_at(rows):
    created_at_values = [
        row.get("created_at")
        for row in rows
        if row.get("created_at")
    ]

    return min(created_at_values) if created_at_values else None


def group_episode_watch_history(rows):
    groups = {}

    for row in rows or []:
        key = (
            row.get("date_earliest"),
            row.get("date_latest"),
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
                item[0][0] or "",
                item[0][1] or "",
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


def sort_watch_history_entries(entries, release_date=None):
    return sorted(
        entries,
        key=lambda entry: watch_history_sort_key(entry, release_date),
        reverse=True,
    )


def watch_history_sort_key(event, release_date=None):
    estimated_date, confidence = estimate_watch_history_sort_date(
        event,
        release_date,
    )

    return (
        estimated_date,
        confidence,
        datetime_sort_key(event.get("created_at")),
        watch_history_identity_sort_key(event),
    )


def estimate_watch_history_sort_date(event, release_date=None):
    """Return an estimated date ordinal and its confidence for sorting.

    Confidence levels are exact date (3), explicit range (2), one explicit
    bound (1), and a created-at proxy or fully unknown date (0).
    """
    earliest = parse_date(event.get("date_earliest"))
    latest = parse_date(event.get("date_latest"))
    created_date = parse_date(event.get("created_at"))
    media_release_date = parse_date(release_date)

    if earliest is not None and latest is not None:
        lower_bound, upper_bound = sorted((earliest, latest))
        confidence = 3 if lower_bound == upper_bound else 2
        return midpoint_date_ordinal(lower_bound, upper_bound), confidence

    if earliest is not None:
        upper_bound = (
            created_date
            if created_date is not None and created_date >= earliest
            else earliest
        )
        return midpoint_date_ordinal(earliest, upper_bound), 1

    if latest is not None:
        lower_bound = (
            media_release_date
            if media_release_date is not None and media_release_date <= latest
            else latest
        )
        return midpoint_date_ordinal(lower_bound, latest), 1

    if created_date is not None:
        return float(created_date.toordinal()), 0

    return 0.0, 0


def midpoint_date_ordinal(lower_bound, upper_bound):
    return (lower_bound.toordinal() + upper_bound.toordinal()) / 2


def datetime_sort_key(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif value:
        try:
            parsed = datetime.fromisoformat(
                str(value).strip().replace("Z", "+00:00")
            )
        except ValueError:
            parsed = None
    else:
        parsed = None

    if parsed is None:
        return (0, 0, 0, 0, 0, 0, 0)

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return (
        parsed.year,
        parsed.month,
        parsed.day,
        parsed.hour,
        parsed.minute,
        parsed.second,
        parsed.microsecond,
    )


def watch_history_identity_sort_key(event):
    identity_values = [
        event.get("id"),
        event.get("watch_history_id"),
        *(event.get("watch_history_ids") or []),
    ]
    watch_history = event.get("watch_history") or {}
    identity_values.extend((
        watch_history.get("id"),
        watch_history.get("watch_history_id"),
    ))

    numeric_ids = []

    for value in identity_values:
        if isinstance(value, int) and not isinstance(value, bool):
            numeric_ids.append(value)
        elif isinstance(value, str) and value.isdecimal():
            numeric_ids.append(int(value))

    fallback_index = event.get("watch_history_index")

    if not numeric_ids and isinstance(fallback_index, int):
        numeric_ids.append(fallback_index)

    return max(numeric_ids) if numeric_ids else 0


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
        return f"~{label}"

    return label


def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        parsed = datetime.fromisoformat(
            str(value).strip().replace("Z", "+00:00")
        )
    except ValueError:
        return None

    return parsed.date()


def format_date_range(earliest, latest):
    if earliest == latest:
        return earliest.strftime("%d %b %Y, %a").lstrip("0")

    if earliest.year == latest.year and earliest.month == latest.month:
        return earliest.strftime("%b %Y")

    if earliest.year == latest.year:
        if (
            earliest.month == 1
            and earliest.day == 1
            and latest.month == 12
            and latest.day == 31
        ):
            return str(earliest.year)

        return f"{earliest:%b}-{latest:%b %Y}"

    return f"{earliest.year}-{latest.year}"


def is_empty_metadata_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
