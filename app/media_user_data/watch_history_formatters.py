from __future__ import annotations

from datetime import date, datetime, timezone


def build_watch_history_display_entries(media_draft):
    metadata = media_draft.get("metadata") or {}
    context = media_draft.get("series_view") or {}
    entries = []
    for event in (media_draft.get("user_data") or {}).get("watch_history", []):
        items = event.get("items") or []
        if metadata.get("media_type") == "episode" and not any(
            (i.get("media_id") == media_draft.get("media_id") if media_draft.get("media_id") is not None
             else i.get("tmdb_id") == metadata.get("tmdb_id")) for i in items
        ):
            continue
        episodic = bool(items) and items[0].get("media_type") == "episode"
        release_date = metadata.get("release_date")
        if metadata.get("media_type") == "series":
            release_date = (context.get("summary") or {}).get("first_air_date") or release_date
        elif episodic and len(items) > 1:
            release_date = ((context.get("summary") or {}).get("first_air_date")
                            or (context.get("metadata") or {}).get("release_date"))
        text = format_watch_history_entry(event, release_date)
        if episodic and (metadata.get("media_type") == "series" or len(items) > 1):
            text += " · " + format_episode_ranges(items)
        elif items and items[0].get("media_type") == "series":
            text += " · no episode info"
        entries.append({**event, "text": text, "release_date": release_date,
                        "kind": "episode_group" if episodic else "media_event"})
    return sorted(entries, key=lambda e: watch_history_sort_key(e, e.get("release_date")), reverse=True)


def build_watch_history_display_lines(media_draft):
    return [entry["text"] for entry in build_watch_history_display_entries(media_draft)]


def build_series_watch_history_entries(media_draft):
    return build_watch_history_display_entries(media_draft)


def build_series_watch_history_lines(media_draft):
    return build_watch_history_display_lines(media_draft)


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
    if event.get("id") is not None:
        return (1, int(event["id"]), "")
    return (0, 0, event.get("draft_id") or "")


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
