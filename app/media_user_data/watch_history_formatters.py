from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

from .watch_history import episode_sort_key, normalize_watch_date


BoundarySource = Literal["date_earliest", "date_latest", "release_date", "created_at"]


@dataclass(frozen=True)
class WatchInterval:
    earliest: date | None
    latest: date | None
    earliest_source: BoundarySource | None
    latest_source: BoundarySource | None
    specificity: int

    @property
    def approximate(self):
        return self.specificity < 2

    @property
    def anchor(self):
        if self.earliest is None:
            return 0.0
        if self.latest_source == "date_latest":
            return midpoint_date_ordinal(self.earliest, self.latest)
        return float(self.earliest.toordinal())

    @property
    def label(self):
        label = (format_date_range(self.earliest, self.latest)
                 if self.earliest is not None else "unknown date")
        return f"~{label}" if self.approximate else label


def watch_history_release_date(event, release_date=None):
    """Episode entries use their first item's release, never the series release."""
    episodes = [item for item in (event.get("items") or [])
                if item.get("media_type") == "episode"]
    if episodes:
        return min(episodes, key=episode_sort_key).get("release_date")
    return release_date


def _explicit_date(value):
    if isinstance(value, date):
        return parse_date(value)
    normalized, error = normalize_watch_date(value)
    if error:
        raise ValueError(error)
    return parse_date(normalized)


def resolve_watch_interval(event, release_date=None):
    """Resolve once, retaining actual boundary sources even after collapse."""
    earliest = _explicit_date(event.get("date_earliest"))
    latest = _explicit_date(event.get("date_latest"))
    if earliest is not None and latest is not None and latest < earliest:
        raise ValueError("Latest date must be on or after earliest date.")
    if earliest is not None and latest is not None:
        specificity = 3 if earliest == latest else 2
    else:
        specificity = int(earliest is not None or latest is not None)
    lower = earliest or parse_date(watch_history_release_date(event, release_date))
    upper = latest or parse_date(event.get("created_at"))
    lower_source = "date_earliest" if earliest else "release_date"
    upper_source = "date_latest" if latest else "created_at"

    if earliest and (upper is None or upper < earliest):
        upper, upper_source = earliest, "date_earliest"
    elif latest and (lower is None or lower > latest):
        lower, lower_source = latest, "date_latest"
    elif not earliest and not latest:
        if lower is None:
            lower, lower_source = upper, upper_source
        if upper is None or (lower is not None and lower > upper):
            upper, upper_source = lower, lower_source

    return WatchInterval(lower, upper, lower_source if lower else None,
                         upper_source if upper else None, specificity)


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
        release_date = watch_history_release_date(event, release_date)
        interval = resolve_watch_interval(event, release_date)
        show_episodes = episodic and (metadata.get("media_type") == "series" or len(items) > 1)
        text = format_watch_history_caption(interval.label, items if show_episodes else ())
        if items and items[0].get("media_type") == "series":
            text += " · no episode info"
        entries.append({**event, "text": text, "release_date": release_date,
                        "sort_key": watch_history_sort_key(event, interval=interval),
                        "kind": "episode_group" if episodic else "media_event"})
    return sorted(entries, key=lambda e: e["sort_key"], reverse=True)


def build_watch_history_display_lines(media_draft):
    return [entry["text"] for entry in build_watch_history_display_entries(media_draft)]


def build_series_watch_history_entries(media_draft):
    return build_watch_history_display_entries(media_draft)


def build_series_watch_history_lines(media_draft):
    return build_watch_history_display_lines(media_draft)


def format_watch_history_caption(date_label, episodes=()):
    """Compose a resolved date and optional episode selection without re-sorting."""
    if episodes:
        return f"{date_label} · {format_episode_ranges(episodes)}"
    return date_label


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


def watch_history_sort_key(event, release_date=None, *, interval=None):
    interval = interval or resolve_watch_interval(event, release_date)
    return (
        interval.anchor,
        interval.specificity,
        datetime_sort_key(event.get("created_at")),
        watch_history_identity_sort_key(event),
    )


def estimate_watch_history_sort_date(event, release_date=None):
    """Compatibility adapter returning the timeline anchor and specificity."""
    interval = resolve_watch_interval(event, release_date)
    return interval.anchor, interval.specificity


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
    return resolve_watch_interval(event, release_date).label


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
