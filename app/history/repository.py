from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.media_user_data.watch_history_formatters import (
    earliest_created_at,
    format_episode_ranges,
    format_watch_history_entry,
    watch_history_sort_key,
)


HISTORY_DEFAULT_FILTER_TEXT = "All watch history entries, in chronological order"


@dataclass(frozen=True)
class HistoryEntry:
    key: tuple[Any, ...]
    kind: str
    watch_history_ids: tuple[int, ...]
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
    is_collection_pick: bool | None
    episodes: tuple[dict[str, Any], ...] = ()


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


def _project_history_entries(rows) -> list[HistoryEntry]:
    direct_entries = []
    episode_groups = {}

    for row in rows:
        if (
            row["owner_media_type"] == "episode"
            and row.get("series_id") is not None
        ):
            key = (
                row["series_id"],
                row["date_earliest"],
                row["date_latest"],
            )
            episode_groups.setdefault(key, []).append(row)
        else:
            direct_entries.append(_build_direct_entry(row))

    grouped_entries = [
        _build_episode_group_entry(group)
        for group in episode_groups.values()
    ]
    return direct_entries + grouped_entries


def _build_direct_entry(row) -> HistoryEntry:
    event = _watch_event(row)
    release_date = (
        row.get("series_first_air_date")
        if row["owner_media_type"] == "series"
        else None
    ) or row.get("owner_release_date")
    history_id = row["watch_history_id"]

    return HistoryEntry(
        key=("media_event", history_id),
        kind="media_event",
        watch_history_ids=(history_id,),
        owner_media_ids=(row["owner_media_id"],),
        state_media_id=row["display_media_id"],
        details_media_id=row["display_media_id"],
        title=row["display_title"],
        date_earliest=row.get("date_earliest"),
        date_latest=row.get("date_latest"),
        created_at=row.get("created_at"),
        release_date=release_date,
        formatted_date=format_watch_history_entry(
            event,
            release_date=release_date,
        ),
        sort_key=watch_history_sort_key(event, release_date),
        poster=choose_history_poster(row),
        media_type=row["display_media_type"],
        watch_state=row.get("display_watch_state"),
        impression=row.get("display_impression"),
        is_collection_pick=_optional_bool(
            row.get("display_is_collection_pick")
        ),
    )


def _build_episode_group_entry(rows) -> HistoryEntry:
    rows = sorted(
        rows,
        key=lambda row: (
            row.get("season_num") or 0,
            row.get("episode_num") or 0,
            row["watch_history_id"],
        ),
    )
    representative = rows[0]
    history_ids = tuple(row["watch_history_id"] for row in rows)
    owner_media_ids = tuple(dict.fromkeys(
        row["owner_media_id"]
        for row in rows
    ))

    if len(owner_media_ids) == 1:
        return _build_single_episode_entry(
            rows,
            owner_media_ids[0],
        )

    release_date = (
        representative.get("series_first_air_date")
        or representative.get("display_release_date")
    )
    created_at = earliest_created_at(rows)
    event = {
        "date_earliest": representative.get("date_earliest"),
        "date_latest": representative.get("date_latest"),
        "created_at": created_at,
        "watch_history_ids": history_ids,
    }
    episodes = tuple(
        {
            "media_id": row["owner_media_id"],
            "watch_history_id": row["watch_history_id"],
            "season_num": row.get("season_num"),
            "episode_num": row.get("episode_num"),
        }
        for row in rows
    )
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
        key=(
            "episode_group",
            representative["series_id"],
            history_ids,
        ),
        kind="episode_group",
        watch_history_ids=history_ids,
        owner_media_ids=owner_media_ids,
        state_media_id=representative["display_media_id"],
        details_media_id=representative["display_media_id"],
        title=f"{representative['display_title']} ({episode_ranges})",
        date_earliest=representative.get("date_earliest"),
        date_latest=representative.get("date_latest"),
        created_at=created_at,
        release_date=release_date,
        formatted_date=format_watch_history_entry(
            event,
            release_date=release_date,
        ),
        sort_key=watch_history_sort_key(event, release_date),
        poster=poster,
        media_type=representative["display_media_type"],
        watch_state=representative.get("display_watch_state"),
        impression=representative.get("display_impression"),
        is_collection_pick=_optional_bool(
            representative.get("display_is_collection_pick")
        ),
        episodes=episodes,
    )


def _build_single_episode_entry(rows, episode_media_id) -> HistoryEntry:
    representative = rows[0]
    history_ids = tuple(row["watch_history_id"] for row in rows)
    created_at = earliest_created_at(rows)
    event = {
        "date_earliest": representative.get("date_earliest"),
        "date_latest": representative.get("date_latest"),
        "created_at": created_at,
        "watch_history_ids": history_ids,
    }
    episodes = tuple(
        {
            "media_id": row["owner_media_id"],
            "watch_history_id": row["watch_history_id"],
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
    release_date = representative.get("owner_release_date")

    return HistoryEntry(
        key=("episode_event", episode_media_id, history_ids),
        kind="episode_event",
        watch_history_ids=history_ids,
        owner_media_ids=(episode_media_id,),
        state_media_id=episode_media_id,
        details_media_id=episode_media_id,
        title=f"{series_title} ({episode_code}) – {episode_title}",
        date_earliest=representative.get("date_earliest"),
        date_latest=representative.get("date_latest"),
        created_at=created_at,
        release_date=release_date,
        formatted_date=format_watch_history_entry(
            event,
            release_date=release_date,
        ),
        sort_key=watch_history_sort_key(event, release_date),
        poster=poster,
        media_type=representative["owner_media_type"],
        watch_state=representative.get("owner_watch_state"),
        impression=representative.get("owner_impression"),
        is_collection_pick=_optional_bool(
            representative.get("owner_is_collection_pick")
        ),
        episodes=episodes,
    )


def _watch_event(row):
    return {
        "id": row["watch_history_id"],
        "date_earliest": row.get("date_earliest"),
        "date_latest": row.get("date_latest"),
        "created_at": row.get("created_at"),
    }


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
        wh.id AS watch_history_id,
        wh.media_id AS owner_media_id,
        wh.date_earliest,
        wh.date_latest,
        wh.created_at,
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
        owner_state.watch_state AS owner_watch_state,
        owner_state.impression AS owner_impression,
        owner_state.is_collection_pick AS owner_is_collection_pick,
        display_state.watch_state AS display_watch_state,
        display_state.impression AS display_impression,
        display_state.is_collection_pick AS display_is_collection_pick,
        owner_poster.filename AS owner_poster_filename,
        owner_poster.source AS owner_poster_source,
        owner_poster.curation_status AS owner_poster_curation_status,
        owner_poster.is_default AS owner_poster_is_default,
        season_poster.filename AS season_poster_filename,
        season_poster.source AS season_poster_source,
        season_poster.curation_status AS season_poster_curation_status,
        season_poster.is_default AS season_poster_is_default,
        poster.filename AS poster_filename,
        poster.source AS poster_source,
        poster.curation_status AS poster_curation_status,
        poster.is_default AS poster_is_default
    FROM watch_history wh
    JOIN media owner
        ON owner.id = wh.media_id
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
