from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from app.media_tooltip import format_media_tooltip
from app.media_user_data.watch_history_formatters import (
    format_episode_ranges,
    format_watch_history_caption,
    resolve_watch_interval,
    watch_history_sort_key,
    watch_history_release_date,
)


HISTORY_DEFAULT_FILTER_TEXT = "All watch history entries, in chronological order"


@dataclass(frozen=True)
class HistoryEntry:
    key: tuple[Any, ...]
    kind: str
    entry_id: int
    owner_media_ids: tuple[int, ...]
    state_media_id: int
    details_media_id: int
    title: str
    date_earliest: str | None
    date_latest: str | None
    created_at: str | None
    release_date: str | None
    formatted_date: str
    sort_key: tuple[Any, ...]
    poster: dict[str, Any] | None
    media_type: str
    watch_state: str | None
    impression: str | None
    is_cabinet_worthy: bool | None
    episodes: tuple[dict[str, Any], ...] = ()
    updated_at: str | None = None
    footer_text: str = ""
    tooltip_text: str = ""
    poster_collections: tuple[tuple[dict[str, Any], ...], ...] = ()


def load_default_history_entries(conn) -> list[HistoryEntry]:
    """Load and project the default History view without building media drafts."""
    rows = [
        dict(row)
        for row in conn.execute(_DEFAULT_HISTORY_QUERY).fetchall()
    ]
    entries = _project_history_entries(rows)
    return sorted(entries, key=lambda entry: entry.sort_key, reverse=True)


def choose_history_poster(
    row,
    *,
    prefix="poster",
) -> dict[str, Any] | None:
    filename = row.get(f"{prefix}_filename")

    if not filename:
        return None

    return {
        "filename": filename,
        "source": row.get(f"{prefix}_source"),
        "curation_status": row.get(f"{prefix}_curation_status"),
        "is_default": bool(row.get(f"{prefix}_is_default")),
    }


def _poster_collection(row, prefix="poster"):
    posters = json.loads(row.get(f"{prefix}_candidates") or "[]")
    return tuple(sorted(posters, key=lambda poster: (
        0 if poster["is_default"] and poster["curation_status"] == "selected"
        else 1 if poster["curation_status"] == "selected" else 2,
        poster["id"],
    )))


def _project_history_entries(rows) -> list[HistoryEntry]:
    by_entry = {}
    for row in rows:
        by_entry.setdefault(row["entry_id"], []).append(row)
    return [_build_episode_group_entry(group) if group[0]["owner_media_type"] == "episode"
            else _build_direct_entry(group[0]) for group in by_entry.values()]


def _build_direct_entry(row) -> HistoryEntry:
    event = _watch_event(row)
    release_date = (
        row.get("series_first_air_date")
        if row["owner_media_type"] == "series"
        else None
    ) or row.get("owner_release_date")
    interval = resolve_watch_interval(event, release_date)
    history_id = row["entry_id"]

    return HistoryEntry(
        key=("watch_history_entry", history_id),
        kind="media_event",
        entry_id=history_id,
        owner_media_ids=(row["owner_media_id"],),
        state_media_id=row["display_media_id"],
        details_media_id=row["display_media_id"],
        title=row["display_title"],
        date_earliest=row.get("date_earliest"),
        date_latest=row.get("date_latest"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        release_date=release_date,
        formatted_date=interval.label,
        footer_text=interval.label,
        tooltip_text=_history_tooltip(row),
        sort_key=watch_history_sort_key(event, interval=interval),
        poster=choose_history_poster(row),
        poster_collections=(_poster_collection(row),),
        media_type=row["display_media_type"],
        watch_state=row.get("display_watch_state"),
        impression=row.get("display_impression"),
        is_cabinet_worthy=_optional_bool(
            row.get("display_is_cabinet_worthy")
        ),
    )


def _build_episode_group_entry(rows) -> HistoryEntry:
    rows = sorted(
        rows,
        key=lambda row: (
            row.get("season_num") or 0,
            row.get("episode_num") or 0,
            row["entry_id"],
        ),
    )
    representative = rows[0]
    owner_media_ids = tuple(dict.fromkeys(
        row["owner_media_id"]
        for row in rows
    ))

    if len(owner_media_ids) == 1:
        return _build_single_episode_entry(
            rows,
            owner_media_ids[0],
        )

    created_at = representative.get("created_at")
    event = _episode_watch_event(rows)
    release_date = watch_history_release_date(event)
    episodes = tuple(
        {
            "media_id": row["owner_media_id"],
            "id": row["item_id"],
            "season_num": row.get("season_num"),
            "episode_num": row.get("episode_num"),
        }
        for row in rows
    )
    interval = resolve_watch_interval(event, release_date)
    episode_ranges = format_episode_ranges(episodes)
    season_numbers = {
        row.get("season_num")
        for row in rows
    }
    poster = choose_history_poster(representative)

    if len(season_numbers) == 1:
        poster = (
            choose_history_poster(
                representative,
                prefix="season_poster",
            )
            or poster
        )

    return HistoryEntry(
        key=("watch_history_entry", representative["entry_id"]),
        kind="episode_group",
        entry_id=representative["entry_id"],
        owner_media_ids=owner_media_ids,
        state_media_id=representative["display_media_id"],
        details_media_id=representative["display_media_id"],
        title=f"{representative['display_title']} ({episode_ranges})",
        date_earliest=representative.get("date_earliest"),
        date_latest=representative.get("date_latest"),
        created_at=created_at,
        updated_at=representative.get("updated_at"),
        release_date=release_date,
        formatted_date=interval.label,
        footer_text=format_watch_history_caption(interval.label, episodes),
        tooltip_text=_history_tooltip(representative),
        sort_key=watch_history_sort_key(event, interval=interval),
        poster=poster,
        poster_collections=(
            (_poster_collection(representative, "season_poster"),
             _poster_collection(representative))
            if len(season_numbers) == 1
            else (_poster_collection(representative),)
        ),
        media_type=representative["display_media_type"],
        watch_state=representative.get("display_watch_state"),
        impression=representative.get("display_impression"),
        is_cabinet_worthy=_optional_bool(
            representative.get("display_is_cabinet_worthy")
        ),
        episodes=episodes,
    )


def _build_single_episode_entry(rows, episode_media_id) -> HistoryEntry:
    representative = rows[0]
    created_at = representative.get("created_at")
    event = _episode_watch_event(rows)
    release_date = watch_history_release_date(event)
    episodes = tuple(
        {
            "media_id": row["owner_media_id"],
            "id": row["item_id"],
            "season_num": row.get("season_num"),
            "episode_num": row.get("episode_num"),
        }
        for row in rows
    )
    episode_code = format_episode_ranges(episodes)
    series_title = representative.get("display_title") or "Series"
    episode_title = representative.get("owner_title") or "Untitled episode"
    poster = (
        choose_history_poster(
            representative,
            prefix="owner_poster",
        )
        or choose_history_poster(
            representative,
            prefix="season_poster",
        )
        or choose_history_poster(representative)
    )
    interval = resolve_watch_interval(event, release_date)

    return HistoryEntry(
        key=("watch_history_entry", representative["entry_id"]),
        kind="episode_event",
        entry_id=representative["entry_id"],
        owner_media_ids=(episode_media_id,),
        state_media_id=episode_media_id,
        details_media_id=episode_media_id,
        title=f"{series_title} ({episode_code}) – {episode_title}",
        date_earliest=representative.get("date_earliest"),
        date_latest=representative.get("date_latest"),
        created_at=created_at,
        updated_at=representative.get("updated_at"),
        release_date=release_date,
        formatted_date=interval.label,
        footer_text=format_watch_history_caption(interval.label, episodes),
        tooltip_text=_history_tooltip(representative, single_episode=True),
        sort_key=watch_history_sort_key(event, interval=interval),
        poster=poster,
        poster_collections=(
            _poster_collection(representative, "owner_poster"),
            _poster_collection(representative, "season_poster"),
            _poster_collection(representative),
        ),
        media_type=representative["owner_media_type"],
        watch_state=representative.get("owner_watch_state"),
        impression=representative.get("owner_impression"),
        is_cabinet_worthy=_optional_bool(
            representative.get("owner_is_cabinet_worthy")
        ),
        episodes=episodes,
    )


def _history_tooltip(row, *, single_episode=False):
    if single_episode:
        return format_media_tooltip(
            row.get("owner_title"), "episode", row.get("owner_release_date"),
            series_title=row["display_title"],
            season_num=row.get("season_num"), episode_num=row.get("episode_num"),
        )
    return format_media_tooltip(
        row["display_title"], row["display_media_type"],
        row.get("display_release_date") if row["display_media_type"] == "series"
        else row.get("owner_release_date"),
        first_air_date=row.get("series_first_air_date"),
        last_air_date=row.get("series_last_air_date"),
    )


def _watch_event(row):
    return {
        "id": row["entry_id"],
        "date_earliest": row.get("date_earliest"),
        "date_latest": row.get("date_latest"),
        "created_at": row.get("created_at"),
    }


def _episode_watch_event(rows):
    event = _watch_event(rows[0])
    event["items"] = [
        {"media_type": "episode", "season_num": row.get("season_num"),
         "episode_num": row.get("episode_num"), "release_date": row.get("owner_release_date")}
        for row in rows
    ]
    return event


def _optional_bool(value):
    return None if value is None else bool(value)


_DEFAULT_HISTORY_QUERY = """
    WITH ranked_posters AS (
        SELECT
            mp.media_id,
            mp.filename,
            mp.source,
            mp.curation_status,
            mp.is_default,
            json_group_array(json_object(
                'id', mp.id, 'filename', mp.filename, 'source', mp.source,
                'curation_status', mp.curation_status, 'is_default', mp.is_default
            )) OVER (PARTITION BY mp.media_id) AS candidates,
            ROW_NUMBER() OVER (
                PARTITION BY mp.media_id
                ORDER BY
                    CASE
                        WHEN mp.is_default = 1
                             AND mp.curation_status = 'selected'
                            THEN 0
                        WHEN mp.curation_status = 'selected'
                            THEN 1
                        WHEN mp.curation_status = 'pending'
                            THEN 2
                        ELSE 3
                    END,
                    mp.id
            ) AS poster_rank
        FROM media_posters mp
        WHERE mp.curation_status IN ('selected', 'pending')
    ),
    ranked_season_posters AS (
        SELECT
            sp.series_id,
            sp.season_num,
            sp.filename,
            sp.source,
            sp.curation_status,
            sp.is_default,
            json_group_array(json_object(
                'id', sp.id, 'filename', sp.filename, 'source', sp.source,
                'curation_status', sp.curation_status, 'is_default', sp.is_default
            )) OVER (PARTITION BY sp.series_id, sp.season_num) AS candidates,
            ROW_NUMBER() OVER (
                PARTITION BY sp.series_id, sp.season_num
                ORDER BY
                    CASE
                        WHEN sp.is_default = 1
                             AND sp.curation_status = 'selected'
                            THEN 0
                        WHEN sp.curation_status = 'selected'
                            THEN 1
                        WHEN sp.curation_status = 'pending'
                            THEN 2
                        ELSE 3
                    END,
                    sp.id
            ) AS poster_rank
        FROM season_posters sp
        WHERE sp.curation_status IN ('selected', 'pending')
    )
    SELECT
        wh.id AS entry_id,
        wi.id AS item_id,
        wi.media_id AS owner_media_id,
        wh.date_earliest,
        wh.date_latest,
        wh.created_at,
        wh.updated_at,
        owner.media_type AS owner_media_type,
        owner.title AS owner_title,
        owner.release_date AS owner_release_date,
        ed.series_id,
        ed.season_num,
        ed.episode_num,
        CASE
            WHEN owner.media_type = 'episode'
                THEN COALESCE(series.id, owner.id)
            ELSE owner.id
        END AS display_media_id,
        CASE
            WHEN owner.media_type = 'episode'
                THEN COALESCE(series.media_type, owner.media_type)
            ELSE owner.media_type
        END AS display_media_type,
        CASE
            WHEN owner.media_type = 'episode'
                THEN COALESCE(series.title, owner.title)
            ELSE owner.title
        END AS display_title,
        CASE
            WHEN owner.media_type = 'episode'
                THEN COALESCE(series.release_date, owner.release_date)
            ELSE owner.release_date
        END AS display_release_date,
        summary.first_air_date AS series_first_air_date,
        summary.last_air_date AS series_last_air_date,
        owner_state.watch_state AS owner_watch_state,
        owner_state.impression AS owner_impression,
        owner_state.is_cabinet_worthy AS owner_is_cabinet_worthy,
        display_state.watch_state AS display_watch_state,
        display_state.impression AS display_impression,
        display_state.is_cabinet_worthy AS display_is_cabinet_worthy,
        owner_poster.filename AS owner_poster_filename,
        owner_poster.candidates AS owner_poster_candidates,
        owner_poster.source AS owner_poster_source,
        owner_poster.curation_status AS owner_poster_curation_status,
        owner_poster.is_default AS owner_poster_is_default,
        season_poster.filename AS season_poster_filename,
        season_poster.candidates AS season_poster_candidates,
        season_poster.source AS season_poster_source,
        season_poster.curation_status AS season_poster_curation_status,
        season_poster.is_default AS season_poster_is_default,
        poster.filename AS poster_filename,
        poster.candidates AS poster_candidates,
        poster.source AS poster_source,
        poster.curation_status AS poster_curation_status,
        poster.is_default AS poster_is_default
    FROM watch_history_entry wh
    JOIN watch_history_item wi ON wi.entry_id = wh.id
    JOIN media owner
        ON owner.id = wi.media_id
    LEFT JOIN media_state owner_state
        ON owner_state.media_id = owner.id
    LEFT JOIN episode_details ed
        ON ed.media_id = owner.id
       AND owner.media_type = 'episode'
    LEFT JOIN media series
        ON series.id = ed.series_id
    LEFT JOIN series_summary summary
        ON summary.series_id = CASE
            WHEN owner.media_type = 'episode' THEN series.id
            WHEN owner.media_type = 'series' THEN owner.id
        END
    LEFT JOIN media_state display_state
        ON display_state.media_id = CASE
            WHEN owner.media_type = 'episode'
                THEN COALESCE(series.id, owner.id)
            ELSE owner.id
        END
    LEFT JOIN ranked_posters poster
        ON poster.media_id = CASE
            WHEN owner.media_type = 'episode'
                THEN COALESCE(series.id, owner.id)
            ELSE owner.id
        END
       AND poster.poster_rank = 1
    LEFT JOIN ranked_posters owner_poster
        ON owner_poster.media_id = owner.id
       AND owner_poster.poster_rank = 1
    LEFT JOIN ranked_season_posters season_poster
        ON season_poster.series_id = ed.series_id
       AND season_poster.season_num = ed.season_num
       AND season_poster.poster_rank = 1
"""
