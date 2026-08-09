"""Reconcile complete TMDB metadata snapshots with the local catalog."""

import sqlite3

from .catalog import (
    _replace_people_relation,
    _save_media_genres,
    _save_media_languages,
    _save_media_metadata,
    _save_media_people,
    _save_media_production_companies,
    _save_media_production_countries,
)
from .errors import MetadataRefreshConflict
from .queries import (
    get_db_media_metadata,
    get_db_series_episodes,
    get_db_series_summary,
)

def apply_metadata_refresh(conn, media_id, snapshot):
    """Atomically reconcile a network-complete metadata snapshot.

    Only catalog tables and ``last_tmdb_metadata_checked_at`` are written.  The
    caller owns BEGIN/commit/rollback, so any :class:`MetadataRefreshConflict`
    leaves rollback policy to the job which opened the transaction.
    """
    root = conn.execute(
        """
        SELECT id, tmdb_id, media_type
        FROM media
        WHERE id = ?
        """,
        (media_id,),
    ).fetchone()

    if root is None:
        raise MetadataRefreshConflict(f"media id {media_id} does not exist.")

    metadata = dict(snapshot.get("metadata") or {})
    snapshot_media_type = snapshot.get("media_type") or metadata.get("media_type")
    snapshot_tmdb_id = snapshot.get("tmdb_id") or metadata.get("tmdb_id")

    if (
        snapshot_media_type != root["media_type"]
        or snapshot_tmdb_id != root["tmdb_id"]
        or metadata.get("media_type") != root["media_type"]
        or metadata.get("tmdb_id") != root["tmdb_id"]
    ):
        raise MetadataRefreshConflict(
            f"metadata snapshot identity does not match media id {media_id}."
        )

    checked_at = (
        snapshot.get("checked_at")
        or metadata.get("last_tmdb_metadata_checked_at")
    )
    if not checked_at:
        raise ValueError("metadata refresh snapshot requires checked_at.")

    metadata["last_tmdb_metadata_checked_at"] = checked_at

    if root["media_type"] == "series":
        stats = _apply_series_metadata_refresh(
            conn,
            media_id,
            metadata,
            snapshot.get("regular_episodes") or [],
            checked_at,
        )
    else:
        _apply_complete_root_metadata(conn, media_id, metadata, checked_at)

        if root["media_type"] == "episode":
            _reconcile_refreshed_episode_details(conn, media_id, metadata)

        stats = _metadata_refresh_stats(created=0, updated=0, preserved=0)

    refreshed_media = conn.execute(
        """
        SELECT
            id,
            tmdb_id,
            imdb_id,
            media_type,
            title,
            original_title,
            production_status,
            release_date,
            runtime_min,
            last_tmdb_metadata_checked_at,
            last_tmdb_posters_checked_at,
            last_tmdb_watch_providers_checked_at
        FROM media
        WHERE id = ?
        """,
        (media_id,),
    ).fetchone()
    canonical_metadata = get_db_media_metadata(conn, refreshed_media)
    summary = (
        get_db_series_summary(conn, media_id)
        if root["media_type"] == "series"
        else None
    )
    episodes = (
        get_db_series_episodes(conn, media_id)
        if root["media_type"] == "series"
        else None
    )
    return {
        "media_id": media_id,
        "metadata": canonical_metadata,
        "summary": summary,
        "episodes": episodes,
        "series_view": (
            {"summary": summary, "episodes": episodes}
            if root["media_type"] == "series"
            else None
        ),
        "series_catalog": (
            {"summary": summary, "episodes": episodes}
            if root["media_type"] == "series"
            else None
        ),
        "stats": stats,
    }

def _metadata_refresh_stats(created, updated, preserved):
    return {
        "created": created,
        "updated": updated,
        "absent_preserved": preserved,
        "preserved_missing": preserved,
        "episodes_created": created,
        "episodes_updated": updated,
        "episodes_absent_preserved": preserved,
    }

def _validate_catalog_metadata(metadata):
    for field in ("tmdb_id", "media_type", "title"):
        if metadata.get(field) in (None, ""):
            raise ValueError(f"metadata.{field} is required.")

def _apply_complete_root_metadata(conn, media_id, metadata, checked_at):
    _validate_catalog_metadata(metadata)

    try:
        cursor = conn.execute(
            """
            UPDATE media
            SET
                imdb_id = ?,
                title = ?,
                original_title = ?,
                production_status = ?,
                release_date = ?,
                runtime_min = ?,
                last_tmdb_metadata_checked_at = ?
            WHERE id = ?
              AND tmdb_id = ?
              AND media_type = ?
            """,
            (
                metadata.get("imdb_id"),
                metadata["title"],
                metadata.get("original_title"),
                metadata.get("production_status"),
                metadata.get("release_date"),
                metadata.get("runtime_min"),
                checked_at,
                media_id,
                metadata["tmdb_id"],
                metadata["media_type"],
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise MetadataRefreshConflict(
            "Refreshed metadata conflicts with an existing TMDB or IMDb identity."
        ) from exc

    if cursor.rowcount != 1:
        raise MetadataRefreshConflict(
            f"metadata identity changed for media id {media_id}."
        )

    _save_media_genres(conn, media_id, metadata)
    _save_media_languages(conn, media_id, metadata)
    _save_media_production_countries(conn, media_id, metadata)
    _save_media_production_companies(conn, media_id, metadata)
    _save_media_people(conn, media_id, metadata)

def _reconcile_refreshed_episode_details(conn, media_id, metadata):
    details = metadata.get("episode_details") or {}
    series_tmdb_id = details.get("series_tmdb_id")
    season_num = details.get("season_num")
    episode_num = details.get("episode_num")

    if series_tmdb_id is None or season_num is None or episode_num is None:
        raise MetadataRefreshConflict(
            "Refreshed episode metadata is missing its series position."
        )

    if season_num < 1 or episode_num < 1:
        raise MetadataRefreshConflict("Special episodes cannot be refreshed here.")

    series = conn.execute(
        """
        SELECT id
        FROM media
        WHERE tmdb_id = ? AND media_type = 'series'
        """,
        (series_tmdb_id,),
    ).fetchone()

    if series is None:
        raise MetadataRefreshConflict(
            "The episode's parent series is not present in the local catalog."
        )

    existing_details = conn.execute(
        "SELECT series_id FROM episode_details WHERE media_id = ?",
        (media_id,),
    ).fetchone()

    if (
        existing_details is not None
        and existing_details["series_id"] != series["id"]
    ):
        raise MetadataRefreshConflict(
            "The refreshed episode belongs to a different parent series."
        )

    occupant = conn.execute(
        """
        SELECT media_id
        FROM episode_details
        WHERE series_id = ? AND season_num = ? AND episode_num = ?
        """,
        (series["id"], season_num, episode_num),
    ).fetchone()

    if occupant is not None and occupant["media_id"] != media_id:
        raise MetadataRefreshConflict(
            "The refreshed episode position is occupied; reload the series metadata."
        )

    conn.execute("DELETE FROM episode_details WHERE media_id = ?", (media_id,))
    conn.execute(
        """
        INSERT INTO episode_details (media_id, series_id, season_num, episode_num)
        VALUES (?, ?, ?, ?)
        """,
        (media_id, series["id"], season_num, episode_num),
    )

def _apply_series_metadata_refresh(
    conn,
    series_id,
    series_metadata,
    incoming_episodes,
    checked_at,
):
    incoming = _validate_series_refresh_episodes(
        conn,
        series_id,
        incoming_episodes,
    )
    local_rows = conn.execute(
        """
        SELECT
            e.id AS episode_id,
            e.tmdb_id,
            e.imdb_id,
            ed.season_num,
            ed.episode_num
        FROM episode_details ed
        JOIN media e ON e.id = ed.media_id
        WHERE ed.series_id = ?
        """,
        (series_id,),
    ).fetchall()
    local_by_tmdb = {row["tmdb_id"]: row for row in local_rows}
    local_by_position = {
        (row["season_num"], row["episode_num"]): row
        for row in local_rows
    }
    incoming_tmdb_ids = {item["tmdb_id"] for item in incoming}
    incoming_existing_ids = {
        local_by_tmdb[item["tmdb_id"]]["episode_id"]
        for item in incoming
        if item["tmdb_id"] in local_by_tmdb
    }

    for item in incoming:
        desired_position = (item["season_num"], item["episode_num"])
        occupant = local_by_position.get(desired_position)

        if (
            occupant is not None
            and occupant["episode_id"] not in incoming_existing_ids
        ):
            raise MetadataRefreshConflict(
                "Incoming episode position "
                f"S{item['season_num']}:E{item['episode_num']} is occupied "
                "by a local episode absent from the TMDB snapshot."
            )

    _apply_complete_root_metadata(
        conn,
        series_id,
        series_metadata,
        checked_at,
    )

    if incoming_existing_ids:
        placeholders = ", ".join("?" for _ in incoming_existing_ids)
        conn.execute(
            f"DELETE FROM episode_details WHERE media_id IN ({placeholders})",
            tuple(incoming_existing_ids),
        )

    created = 0
    updated = 0

    for item in incoming:
        metadata = item["metadata"]
        existing = local_by_tmdb.get(item["tmdb_id"])

        if existing is None:
            episode_metadata = dict(metadata)
            episode_metadata["imdb_id"] = None
            episode_metadata["last_tmdb_metadata_checked_at"] = checked_at

            try:
                episode_id = _save_media_metadata(conn, episode_metadata)
            except sqlite3.IntegrityError as exc:
                raise MetadataRefreshConflict(
                    "A new episode conflicts with an existing IMDb identity."
                ) from exc

            created += 1
        else:
            episode_id = existing["episode_id"]
            incoming_imdb_id = metadata.get("imdb_id")

            if (
                incoming_imdb_id
                and existing["imdb_id"]
                and incoming_imdb_id != existing["imdb_id"]
            ):
                raise MetadataRefreshConflict(
                    f"Episode TMDB id {item['tmdb_id']} has conflicting IMDb identity."
                )

            _apply_series_episode_projection(
                conn,
                episode_id,
                metadata,
                checked_at,
            )
            updated += 1

        conn.execute(
            """
            INSERT INTO episode_details (
                media_id,
                series_id,
                season_num,
                episode_num
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                episode_id,
                series_id,
                item["season_num"],
                item["episode_num"],
            ),
        )

    preserved = len(set(local_by_tmdb) - incoming_tmdb_ids)
    return _metadata_refresh_stats(created, updated, preserved)

def _validate_series_refresh_episodes(conn, series_id, episodes):
    normalized = []
    seen_tmdb_ids = set()
    seen_positions = set()
    root = conn.execute(
        "SELECT tmdb_id FROM media WHERE id = ? AND media_type = 'series'",
        (series_id,),
    ).fetchone()

    if root is None:
        raise MetadataRefreshConflict(
            f"series id {series_id} does not exist or is not a series."
        )

    for metadata_source in episodes:
        metadata = dict(metadata_source or {})
        details = metadata.get("episode_details") or {}
        tmdb_id = metadata.get("tmdb_id")
        season_num = details.get("season_num")
        episode_num = details.get("episode_num")

        if (
            metadata.get("media_type") != "episode"
            or tmdb_id is None
            or season_num is None
            or episode_num is None
        ):
            raise MetadataRefreshConflict(
                "Series refresh contains incomplete episode metadata."
            )

        if season_num < 1 or episode_num < 1:
            raise MetadataRefreshConflict(
                "Series refresh contains a special or invalid episode position."
            )

        if tmdb_id in seen_tmdb_ids:
            raise MetadataRefreshConflict(
                f"Series refresh contains duplicate episode TMDB id {tmdb_id}."
            )

        position = (season_num, episode_num)

        if position in seen_positions:
            raise MetadataRefreshConflict(
                "Series refresh contains duplicate position "
                f"S{season_num}:E{episode_num}."
            )

        series_tmdb_id = details.get("series_tmdb_id")

        if series_tmdb_id != root["tmdb_id"]:
            raise MetadataRefreshConflict(
                f"Episode TMDB id {tmdb_id} belongs to another series."
            )

        global_episode = conn.execute(
            """
            SELECT m.id, ed.series_id
            FROM media m
            LEFT JOIN episode_details ed ON ed.media_id = m.id
            WHERE m.tmdb_id = ? AND m.media_type = 'episode'
            """,
            (tmdb_id,),
        ).fetchone()

        if global_episode is not None and global_episode["series_id"] != series_id:
            raise MetadataRefreshConflict(
                f"Episode TMDB id {tmdb_id} belongs to another local series."
            )

        incoming_imdb_id = metadata.get("imdb_id")

        if incoming_imdb_id:
            imdb_owner = conn.execute(
                "SELECT id FROM media WHERE imdb_id = ?",
                (incoming_imdb_id,),
            ).fetchone()

            if (
                imdb_owner is not None
                and (
                    global_episode is None
                    or imdb_owner["id"] != global_episode["id"]
                )
            ):
                raise MetadataRefreshConflict(
                    f"Episode TMDB id {tmdb_id} conflicts with another IMDb identity."
                )

        seen_tmdb_ids.add(tmdb_id)
        seen_positions.add(position)
        normalized.append({
            "tmdb_id": tmdb_id,
            "season_num": season_num,
            "episode_num": episode_num,
            "metadata": metadata,
        })

    return normalized

def _apply_series_episode_projection(conn, episode_id, metadata, checked_at):
    _validate_catalog_metadata(metadata)

    try:
        cursor = conn.execute(
            """
            UPDATE media
            SET
                title = ?,
                original_title = ?,
                production_status = ?,
                release_date = ?,
                runtime_min = ?,
                last_tmdb_metadata_checked_at = ?
            WHERE id = ?
              AND tmdb_id = ?
              AND media_type = 'episode'
            """,
            (
                metadata["title"],
                metadata.get("original_title"),
                metadata.get("production_status"),
                metadata.get("release_date"),
                metadata.get("runtime_min"),
                checked_at,
                episode_id,
                metadata["tmdb_id"],
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise MetadataRefreshConflict(
            f"Episode TMDB id {metadata['tmdb_id']} has conflicting metadata."
        ) from exc

    if cursor.rowcount != 1:
        raise MetadataRefreshConflict(
            f"Episode TMDB id {metadata['tmdb_id']} changed identity."
        )

    _save_media_genres(conn, episode_id, metadata)
    _save_media_languages(conn, episode_id, metadata)
    _save_media_production_countries(conn, episode_id, metadata)
    _save_media_production_companies(conn, episode_id, metadata)
    _replace_people_relation(
        conn,
        table_name="media_creators",
        media_id=episode_id,
        people=metadata.get("creators", []),
    )
