import sqlite3

from app.config import TMDB_MAX_POSTERS_PER_MEDIA
from app.media_lists import (
    DUPLICATE_LIST_NAME_ERROR,
    normalize_list_description,
    validate_list_name,
)
from app.media_notes import validate_note_text
from app.watch_states import validate_watch_state


TMDB_FRESHNESS_COLUMNS = (
    "last_tmdb_metadata_checked_at",
    "last_tmdb_posters_checked_at",
    "last_tmdb_watch_providers_checked_at",
)


class ConcurrentEditError(RuntimeError):
    """Raised when an edited value no longer matches its dialog baseline."""


class MetadataRefreshConflict(RuntimeError):
    """Raised when a TMDB snapshot cannot be reconciled without data loss."""


def get_media_by_id(conn, media_id):
    if media_id is None:
        return None

    cursor = conn.execute(
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
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)


def get_media_by_imdb_id(conn, imdb_id):
    if imdb_id is None:
        return None

    cursor = conn.execute(
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
        WHERE imdb_id = ?
        """,
        (imdb_id,),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)

def get_media_by_tmdb_id(conn, tmdb_id, media_type):
    cursor = conn.execute(
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
        WHERE tmdb_id = ?
          AND media_type = ?
        """,
        (
            tmdb_id,
            media_type,
        ),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)

def get_db_genres(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            g.tmdb_id,
            g.name,
            g.tmdb_scope
        FROM media_genres mg
        JOIN genres g
            ON g.id = mg.genre_id
        WHERE mg.media_id = ?
        ORDER BY g.name
        """,
        (media_id,),
    )

    return [
        {
            "tmdb_id": row["tmdb_id"],
            "name": row["name"],
            "tmdb_scope": row["tmdb_scope"],
        }
        for row in cursor.fetchall()
    ]

def get_db_spoken_languages(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            l.code,
            l.name
        FROM media_spoken_languages msl
        JOIN languages l
            ON l.code = msl.language_code
        WHERE msl.media_id = ?
        ORDER BY l.name
        """,
        (media_id,),
    )

    return [
        {
            "code": row["code"],
            "name": row["name"],
        }
        for row in cursor.fetchall()
    ]

def get_db_origin_language(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            l.code,
            l.name
        FROM media_origin_language mol
        JOIN languages l
            ON l.code = mol.language_code
        WHERE mol.media_id = ?
        """,
        (media_id,),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return {
        "code": row["code"],
        "name": row["name"],
    }

def get_db_production_countries(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            c.code,
            c.name
        FROM media_production_countries mpc
        JOIN countries c
            ON c.code = mpc.country_code
        WHERE mpc.media_id = ?
        ORDER BY c.name
        """,
        (media_id,),
    )

    return [
        {
            "code": row["code"],
            "name": row["name"],
        }
        for row in cursor.fetchall()
    ]

def get_db_production_companies(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            c.tmdb_id,
            c.name
        FROM media_production_companies mpc
        JOIN companies c
            ON c.id = mpc.company_id
        WHERE mpc.media_id = ?
        ORDER BY c.name
        """,
        (media_id,),
    )

    return [
        {
            "tmdb_id": row["tmdb_id"],
            "name": row["name"],
        }
        for row in cursor.fetchall()
    ]

def get_db_directors(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            p.tmdb_id,
            p.name
        FROM media_directors md
        JOIN people p
            ON p.id = md.person_id
        WHERE md.media_id = ?
        ORDER BY p.name
        """,
        (media_id,),
    )

    return [
        {
            "tmdb_id": row["tmdb_id"],
            "name": row["name"],
        }
        for row in cursor.fetchall()
    ]

def get_db_creators(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            p.tmdb_id,
            p.name
        FROM media_creators mc
        JOIN people p
            ON p.id = mc.person_id
        WHERE mc.media_id = ?
        ORDER BY p.name
        """,
        (media_id,),
    )

    return [
        {
            "tmdb_id": row["tmdb_id"],
            "name": row["name"],
        }
        for row in cursor.fetchall()
    ]

def get_db_writers(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            p.tmdb_id,
            p.name,
            mw.job
        FROM media_writers mw
        JOIN people p
            ON p.id = mw.person_id
        WHERE mw.media_id = ?
        ORDER BY
            p.name,
            mw.job
        """,
        (media_id,),
    )

    return [
        {
            "tmdb_id": row["tmdb_id"],
            "name": row["name"],
            "job": row["job"],
        }
        for row in cursor.fetchall()
    ]

def get_db_actors(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            p.tmdb_id,
            p.name,
            ma.character,
            ma.cast_order
        FROM media_actors ma
        JOIN people p
            ON p.id = ma.person_id
        WHERE ma.media_id = ?
        ORDER BY
            ma.cast_order IS NULL,
            ma.cast_order,
            p.name
        """,
        (media_id,),
    )

    return [
        {
            "tmdb_id": row["tmdb_id"],
            "name": row["name"],
            "character": row["character"],
            "cast_order": row["cast_order"],
        }
        for row in cursor.fetchall()
    ]

def get_db_series_summary(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            season_count,
            episode_count,
            first_air_date,
            last_air_date,
            total_runtime_min,
            avg_episode_runtime_min
        FROM series_summary
        WHERE series_id = ?
        """,
        (media_id,),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)

def get_db_series_episode_watch_history(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            series_id,
            episode_id,
            season_num,
            episode_num,
            watch_history_id,
            date_earliest,
            date_latest,
            created_at
        FROM series_episode_watch_history
        WHERE series_id = ?
        ORDER BY
            created_at,
            watch_history_id,
            season_num,
            episode_num
        """,
        (media_id,),
    )

    return [dict(row) for row in cursor.fetchall()]

def get_db_series_episodes(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            ed.series_id AS series_id,
            e.id AS episode_id,
            e.tmdb_id AS tmdb_id,
            ed.season_num AS season_num,
            ed.episode_num AS episode_num,
            e.title AS title,
            e.release_date AS release_date
        FROM episode_details ed
        JOIN media e
            ON e.id = ed.media_id
        WHERE ed.series_id = ?
        ORDER BY
            ed.season_num,
            ed.episode_num
        """,
        (media_id,),
    )

    return [dict(row) for row in cursor.fetchall()]

def get_db_series_view(conn, media_id, media_type):
    if media_type != "series":
        return None

    return {
        "summary": get_db_series_summary(conn, media_id),
        "episodes": get_db_series_episodes(conn, media_id),
        "episode_watch_history": get_db_series_episode_watch_history(
            conn,
            media_id,
        ),
    }

def get_db_episode_details(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            s.tmdb_id AS series_tmdb_id,
            s.imdb_id AS series_imdb_id,
            s.title AS series_title,
            ed.season_num,
            ed.episode_num
        FROM episode_details ed
        JOIN media s
            ON s.id = ed.series_id
        WHERE ed.media_id = ?
        """,
        (media_id,),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)

def get_db_media_metadata(conn, media_from_db):
    media_id = media_from_db["id"]
    media_type = media_from_db["media_type"]

    return {
        "tmdb_id": media_from_db["tmdb_id"],
        "imdb_id": media_from_db["imdb_id"],
        "media_type": media_from_db["media_type"],
        "title": media_from_db["title"],
        "original_title": media_from_db["original_title"],
        "production_status": media_from_db["production_status"],
        "release_date": media_from_db["release_date"],
        "runtime_min": media_from_db["runtime_min"],
        "last_tmdb_metadata_checked_at": _row_get(
            media_from_db,
            "last_tmdb_metadata_checked_at",
        ),
        "last_tmdb_posters_checked_at": _row_get(
            media_from_db,
            "last_tmdb_posters_checked_at",
        ),
        "last_tmdb_watch_providers_checked_at": _row_get(
            media_from_db,
            "last_tmdb_watch_providers_checked_at",
        ),

        "genres": get_db_genres(conn, media_id),
        "spoken_languages": get_db_spoken_languages(conn, media_id),
        "origin_language": get_db_origin_language(conn, media_id),
        "production_countries": get_db_production_countries(conn, media_id),
        "production_companies": get_db_production_companies(conn, media_id),
        "directors": get_db_directors(conn, media_id),
        "creators": get_db_creators(conn, media_id),
        "writers": get_db_writers(conn, media_id),
        "actors": get_db_actors(conn, media_id),

        "episode_details": get_db_episode_details(conn, media_id) if media_type == "episode" else None,
    }


def _row_get(row, key, default=None):
    if hasattr(row, "keys") and key not in row.keys():
        return default

    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return default

def get_db_media_watch_providers(conn, metadata):
    cursor = conn.execute(
        """
        SELECT
            name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'media_watch_providers'
        """
    )

    if cursor.fetchone() is None:
        return []

    cursor = conn.execute(
        """
        SELECT
            provider_tmdb_id,
            provider_name,
            country_code,
            access_type
        FROM media_watch_providers
        WHERE media_id = (
            SELECT id
            FROM media
            WHERE tmdb_id = ?
              AND media_type = ?
        )
        ORDER BY
            CASE access_type
                WHEN 'flatrate' THEN 1
                WHEN 'rent' THEN 2
                WHEN 'buy' THEN 3
                ELSE 4
            END,
            provider_name
        """,
        (
            metadata["tmdb_id"],
            metadata["media_type"],
        ),
    )

    return [
        {
            "provider_tmdb_id": row["provider_tmdb_id"],
            "provider_name": row["provider_name"],
            "country_code": row["country_code"],
            "access_type": row["access_type"],
        }
        for row in cursor.fetchall()
    ]

def _format_db_poster_row(row, scope, series_tmdb_id=None, season_num=None):
    return {
        "scope": scope,
        "filename": row["filename"],
        "source": row["source"],
        "curation_status": row["curation_status"],
        "is_default": bool(row["is_default"]),
        "series_tmdb_id": series_tmdb_id,
        "season_num": season_num,
    }

def _get_db_media_posters_by_media(conn, media_type, tmdb_id, scope="media"):
    cursor = conn.execute(
        """
        SELECT
            mp.filename,
            mp.source,
            mp.curation_status,
            mp.is_default
        FROM media_posters mp
        JOIN media m
            ON m.id = mp.media_id
        WHERE m.tmdb_id = ?
          AND m.media_type = ?
        ORDER BY
            mp.is_default DESC,
            CASE mp.curation_status
                WHEN 'selected' THEN 1
                WHEN 'pending' THEN 2
                WHEN 'failed' THEN 3
                WHEN 'discarded' THEN 4
                ELSE 5
            END,
            mp.filename
        """,
        (
            tmdb_id,
            media_type,
        ),
    )

    return [
        _format_db_poster_row(row, scope)
        for row in cursor.fetchall()
    ]

def _get_db_season_posters(conn, series_tmdb_id, season_num):
    cursor = conn.execute(
        """
        SELECT
            sp.filename,
            sp.source,
            sp.curation_status,
            sp.is_default
        FROM season_posters sp
        JOIN media s
            ON s.id = sp.series_id
        WHERE s.tmdb_id = ?
          AND s.media_type = 'series'
          AND sp.season_num = ?
        ORDER BY
            sp.is_default DESC,
            CASE sp.curation_status
                WHEN 'selected' THEN 1
                WHEN 'pending' THEN 2
                WHEN 'failed' THEN 3
                WHEN 'discarded' THEN 4
                ELSE 5
            END,
            sp.filename
        """,
        (
            series_tmdb_id,
            season_num,
        ),
    )

    return [
        _format_db_poster_row(
            row,
            scope="season",
            series_tmdb_id=series_tmdb_id,
            season_num=season_num,
        )
        for row in cursor.fetchall()
    ]

def get_db_media_posters(conn, metadata):
    media_type = metadata["media_type"]

    if media_type in {"movie", "series"}:
        return _get_db_media_posters_by_media(
            conn,
            media_type=media_type,
            tmdb_id=metadata["tmdb_id"],
        )

    if media_type == "episode":
        episode_details = metadata.get("episode_details") or {}
        series_tmdb_id = episode_details.get("series_tmdb_id")
        season_num = episode_details.get("season_num")

        media_posters = _get_db_media_posters_by_media(
            conn,
            media_type="episode",
            tmdb_id=metadata["tmdb_id"],
        )

        season_posters = []
        series_posters = []

        if series_tmdb_id and season_num is not None:
            season_posters = _get_db_season_posters(
                conn,
                series_tmdb_id=series_tmdb_id,
                season_num=season_num,
            )

        if series_tmdb_id:
            series_posters = _get_db_media_posters_by_media(
                conn,
                media_type="series",
                tmdb_id=series_tmdb_id,
                scope="series",
            )

            for poster in series_posters:
                poster["series_tmdb_id"] = series_tmdb_id

        return media_posters + season_posters + series_posters

    raise ValueError(f"Unsupported media_type: {media_type}")

def get_empty_media_user_data():
    return {
        "watch_state": None,
        "impression": None,
        "is_collection_pick": None,
        "watch_history": [],
        "notes": [],
        "lists": [],
    }

def _get_db_media_id(conn, metadata):
    cursor = conn.execute(
        """
        SELECT id
        FROM media
        WHERE tmdb_id = ?
          AND media_type = ?
        """,
        (
            metadata["tmdb_id"],
            metadata["media_type"],
        ),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return row["id"]

def get_db_media_user_data(conn, metadata):
    media_id = _get_db_media_id(conn, metadata)

    if media_id is None:
        return get_empty_media_user_data()

    user_data = get_empty_media_user_data()

    cursor = conn.execute(
        """
        SELECT
            watch_state,
            impression,
            is_collection_pick
        FROM media_state
        WHERE media_id = ?
        """,
        (media_id,),
    )

    state = cursor.fetchone()

    if state is not None:
        user_data["watch_state"] = state["watch_state"]
        user_data["impression"] = state["impression"]
        user_data["is_collection_pick"] = (
            None
            if state["is_collection_pick"] is None
            else bool(state["is_collection_pick"])
        )

    cursor = conn.execute(
        """
        SELECT
            id,
            date_earliest,
            date_latest,
            created_at
        FROM watch_history
        WHERE media_id = ?
        ORDER BY
            created_at,
            id
        """,
        (media_id,),
    )

    user_data["watch_history"] = [
        {
            "id": row["id"],
            "date_earliest": row["date_earliest"],
            "date_latest": row["date_latest"],
            "created_at": row["created_at"],
        }
        for row in cursor.fetchall()
    ]

    cursor = conn.execute(
        """
        SELECT
            id,
            note,
            created_at
        FROM media_notes
        WHERE media_id = ?
        ORDER BY created_at, id
        """,
        (media_id,),
    )

    user_data["notes"] = [
        {
            "id": row["id"],
            "note": row["note"],
            "created_at": row["created_at"],
        }
        for row in cursor.fetchall()
    ]

    cursor = conn.execute(
        """
        SELECT
            l.id,
            l.name
        FROM media_lists ml
        JOIN lists l
            ON l.id = ml.list_id
        WHERE ml.media_id = ?
        ORDER BY l.name COLLATE NOCASE, l.name, l.id
        """,
        (media_id,),
    )

    user_data["lists"] = [
        {
            "id": row["id"],
            "name": row["name"],
        }
        for row in cursor.fetchall()
    ]

    return user_data


def get_all_lists(conn):
    cursor = conn.execute(
        """
        SELECT
            id,
            name,
            description
        FROM lists
        ORDER BY name COLLATE NOCASE, name, id
        """
    )

    return [dict(row) for row in cursor.fetchall()]


def create_list(conn, name, description=None):
    normalized_name = validate_list_name(name)
    normalized_description = normalize_list_description(description)
    _ensure_unique_list_name(conn, normalized_name)

    try:
        cursor = conn.execute(
            """
            INSERT INTO lists (name, description)
            VALUES (?, ?)
            """,
            (normalized_name, normalized_description),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(DUPLICATE_LIST_NAME_ERROR) from exc

    return {
        "id": cursor.lastrowid,
        "name": normalized_name,
        "description": normalized_description,
    }


def update_list(conn, list_id, name, description=None):
    normalized_name = validate_list_name(name)
    normalized_description = normalize_list_description(description)
    _ensure_unique_list_name(conn, normalized_name, current_list_id=list_id)

    try:
        cursor = conn.execute(
            """
            UPDATE lists
            SET
                name = ?,
                description = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (normalized_name, normalized_description, list_id),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError(DUPLICATE_LIST_NAME_ERROR) from exc

    if cursor.rowcount == 0:
        raise ValueError(f"lists id {list_id} does not exist.")

    return {
        "id": list_id,
        "name": normalized_name,
        "description": normalized_description,
    }


def delete_list(conn, list_id):
    cursor = conn.execute(
        "DELETE FROM lists WHERE id = ?",
        (list_id,),
    )
    return cursor.rowcount > 0


def _ensure_unique_list_name(conn, name, current_list_id=None):
    if current_list_id is None:
        row = conn.execute(
            "SELECT id FROM lists WHERE name = ?",
            (name,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM lists WHERE name = ? AND id != ?",
            (name, current_list_id),
        ).fetchone()

    if row is not None:
        raise ValueError(DUPLICATE_LIST_NAME_ERROR)


def replace_media_watch_providers(conn, media_id, watch_providers, checked_at=None):
    _save_media_watch_providers(conn, media_id, watch_providers)
    update_media_tmdb_watch_providers_checked_at(
        conn,
        media_id,
        checked_at,
    )


def update_media_tmdb_watch_providers_checked_at(conn, media_id, checked_at):
    _update_media_tmdb_freshness(
        conn,
        media_id,
        "last_tmdb_watch_providers_checked_at",
        checked_at,
    )


def update_media_tmdb_posters_checked_at(conn, media_id, checked_at):
    _update_media_tmdb_freshness(
        conn,
        media_id,
        "last_tmdb_posters_checked_at",
        checked_at,
    )


def _update_media_tmdb_freshness(conn, media_id, column_name, checked_at):
    if column_name not in TMDB_FRESHNESS_COLUMNS:
        raise ValueError(f"Unsupported TMDB freshness column: {column_name}")

    if checked_at is None:
        return

    conn.execute(
        f"""
        UPDATE media
        SET {column_name} = ?
        WHERE id = ?
        """,
        (
            checked_at,
            media_id,
        ),
    )


def delete_media(conn, media_id):
    cursor = conn.execute(
        """
        SELECT
            id,
            media_type
        FROM media
        WHERE id = ?
        """,
        (media_id,),
    )
    media = cursor.fetchone()

    if media is None:
        return False

    if media["media_type"] == "series":
        conn.execute(
            """
            DELETE FROM media
            WHERE id IN (
                SELECT media_id
                FROM episode_details
                WHERE series_id = ?
            )
            """,
            (media_id,),
        )

    conn.execute(
        """
        DELETE FROM media
        WHERE id = ?
        """,
        (media_id,),
    )

    return True



########################################################

def save_media_draft(conn, media_draft):
    media_id = save_media_catalog_draft(conn, media_draft)
    _save_media_user_data(
        conn,
        media_id,
        media_draft.get("user_data") or get_empty_media_user_data(),
    )

    return media_id


def save_media_catalog_draft(conn, media_draft):
    metadata = media_draft["metadata"]

    media_id = _save_media_metadata(conn, metadata)
    _save_episode_details(conn, media_id, metadata)
    _save_media_watch_providers(
        conn,
        media_id,
        media_draft.get("watch_providers", []),
    )
    _save_media_posters(
        conn,
        media_id,
        metadata,
        media_draft.get("posters", []),
    )
    media_draft["media_id"] = media_id
    return media_id

def add_media(conn, media_draft):
    return save_media_draft(conn, media_draft)

def _save_media_metadata(conn, metadata):
    media_id = _save_media_row(conn, metadata)

    _save_media_genres(conn, media_id, metadata)
    _save_media_languages(conn, media_id, metadata)
    _save_media_production_countries(conn, media_id, metadata)
    _save_media_production_companies(conn, media_id, metadata)
    _save_media_people(conn, media_id, metadata)

    return media_id

def _save_media_row(conn, metadata):
    required_fields = ("tmdb_id", "media_type", "title")

    for field in required_fields:
        if metadata.get(field) in (None, ""):
            raise ValueError(f"metadata.{field} is required.")

    conn.execute(
        """
        INSERT INTO media (
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (tmdb_id, media_type) DO UPDATE SET
            imdb_id = excluded.imdb_id,
            title = excluded.title,
            original_title = excluded.original_title,
            production_status = excluded.production_status,
            release_date = excluded.release_date,
            runtime_min = excluded.runtime_min,
            last_tmdb_metadata_checked_at = COALESCE(
                excluded.last_tmdb_metadata_checked_at,
                media.last_tmdb_metadata_checked_at
            ),
            last_tmdb_posters_checked_at = COALESCE(
                excluded.last_tmdb_posters_checked_at,
                media.last_tmdb_posters_checked_at
            ),
            last_tmdb_watch_providers_checked_at = COALESCE(
                excluded.last_tmdb_watch_providers_checked_at,
                media.last_tmdb_watch_providers_checked_at
            )
        """,
        (
            metadata["tmdb_id"],
            metadata.get("imdb_id"),
            metadata["media_type"],
            metadata["title"],
            metadata.get("original_title"),
            metadata.get("production_status"),
            metadata.get("release_date"),
            metadata.get("runtime_min"),
            metadata.get("last_tmdb_metadata_checked_at"),
            metadata.get("last_tmdb_posters_checked_at"),
            metadata.get("last_tmdb_watch_providers_checked_at"),
        ),
    )

    return _get_db_media_id(conn, metadata)

def _save_episode_details(conn, media_id, metadata):
    if metadata["media_type"] != "episode":
        conn.execute(
            """
            DELETE FROM episode_details
            WHERE media_id = ?
            """,
            (media_id,),
        )
        return

    episode_details = metadata.get("episode_details") or {}
    series_id = _get_or_create_episode_series_id(conn, episode_details)
    season_num = episode_details.get("season_num")
    episode_num = episode_details.get("episode_num")

    if season_num is None:
        raise ValueError("metadata.episode_details.season_num is required.")

    if episode_num is None:
        raise ValueError("metadata.episode_details.episode_num is required.")

    conn.execute(
        """
        INSERT INTO episode_details (
            media_id,
            series_id,
            season_num,
            episode_num
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT (media_id) DO UPDATE SET
            series_id = excluded.series_id,
            season_num = excluded.season_num,
            episode_num = excluded.episode_num
        """,
        (
            media_id,
            series_id,
            season_num,
            episode_num,
        ),
    )

def _get_or_create_episode_series_id(conn, episode_details):
    series_tmdb_id = episode_details.get("series_tmdb_id")

    if series_tmdb_id is None:
        raise ValueError("metadata.episode_details.series_tmdb_id is required.")

    series_metadata = {
        "tmdb_id": series_tmdb_id,
        "media_type": "series",
    }
    series_id = _get_db_media_id(conn, series_metadata)

    if series_id is not None:
        return series_id

    series_imdb_id = episode_details.get("series_imdb_id")
    series_title = episode_details.get("series_title")

    if not series_title:
        raise ValueError("metadata.episode_details.series_title is required.")

    return _save_media_row(conn, {
        "tmdb_id": series_tmdb_id,
        "imdb_id": series_imdb_id,
        "media_type": "series",
        "title": series_title,
        "original_title": series_title,
        "production_status": None,
        "release_date": None,
        "runtime_min": None,
    })

def _save_media_genres(conn, media_id, metadata):
    conn.execute(
        """
        DELETE FROM media_genres
        WHERE media_id = ?
        """,
        (media_id,),
    )

    for genre in metadata.get("genres", []):
        genre_id = _get_or_create_genre_id(
            conn,
            genre,
            metadata["media_type"],
        )

        if genre_id is None:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO media_genres (
                media_id,
                genre_id
            )
            VALUES (?, ?)
            """,
            (
                media_id,
                genre_id,
            ),
        )

def _get_or_create_genre_id(conn, genre, media_type):
    tmdb_id = genre.get("tmdb_id")
    name = genre.get("name")
    tmdb_scope = genre.get("tmdb_scope")

    if tmdb_scope is None:
        tmdb_scope = "series" if media_type == "episode" else media_type

    if tmdb_id is None or not name:
        return None

    conn.execute(
        """
        INSERT INTO genres (
            tmdb_id,
            name,
            tmdb_scope
        )
        VALUES (?, ?, ?)
        ON CONFLICT (tmdb_id, tmdb_scope) DO UPDATE SET
            name = excluded.name
        """,
        (
            tmdb_id,
            name,
            tmdb_scope,
        ),
    )

    cursor = conn.execute(
        """
        SELECT id
        FROM genres
        WHERE tmdb_id = ?
          AND tmdb_scope = ?
        """,
        (
            tmdb_id,
            tmdb_scope,
        ),
    )

    return cursor.fetchone()["id"]

def _save_media_languages(conn, media_id, metadata):
    conn.execute(
        """
        DELETE FROM media_spoken_languages
        WHERE media_id = ?
        """,
        (media_id,),
    )

    for language in metadata.get("spoken_languages", []):
        language_code = _save_language(conn, language)

        if language_code is None:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO media_spoken_languages (
                media_id,
                language_code
            )
            VALUES (?, ?)
            """,
            (
                media_id,
                language_code,
            ),
        )

    conn.execute(
        """
        DELETE FROM media_origin_language
        WHERE media_id = ?
        """,
        (media_id,),
    )

    origin_language = metadata.get("origin_language")

    if origin_language:
        origin_language_code = _save_language(conn, origin_language)

        if origin_language_code is not None:
            conn.execute(
                """
                INSERT INTO media_origin_language (
                    media_id,
                    language_code
                )
                VALUES (?, ?)
                ON CONFLICT (media_id) DO UPDATE SET
                    language_code = excluded.language_code
                """,
                (
                    media_id,
                    origin_language_code,
                ),
            )

def _save_language(conn, language):
    code = language.get("code")

    if not code:
        return None

    name = language.get("name")

    if name:
        conn.execute(
            """
            INSERT INTO languages (
                code,
                name
            )
            VALUES (?, ?)
            ON CONFLICT (code) DO UPDATE SET
                name = excluded.name
            """,
            (
                code,
                name,
            ),
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO languages (
                code,
                name
            )
            VALUES (?, ?)
            """,
            (
                code,
                code,
            ),
        )

    return code

def _save_media_production_countries(conn, media_id, metadata):
    conn.execute(
        """
        DELETE FROM media_production_countries
        WHERE media_id = ?
        """,
        (media_id,),
    )

    for country in metadata.get("production_countries", []):
        country_code = _save_country(conn, country)

        if country_code is None:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO media_production_countries (
                media_id,
                country_code
            )
            VALUES (?, ?)
            """,
            (
                media_id,
                country_code,
            ),
        )

def _save_country(conn, country):
    code = country.get("code")

    if not code:
        return None

    name = country.get("name")

    if name:
        conn.execute(
            """
            INSERT INTO countries (
                code,
                name
            )
            VALUES (?, ?)
            ON CONFLICT (code) DO UPDATE SET
                name = excluded.name
            """,
            (
                code,
                name,
            ),
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO countries (
                code,
                name
            )
            VALUES (?, ?)
            """,
            (
                code,
                code,
            ),
        )

    return code

def _save_media_production_companies(conn, media_id, metadata):
    conn.execute(
        """
        DELETE FROM media_production_companies
        WHERE media_id = ?
        """,
        (media_id,),
    )

    for company in metadata.get("production_companies", []):
        company_id = _get_or_create_company_id(conn, company)

        if company_id is None:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO media_production_companies (
                media_id,
                company_id
            )
            VALUES (?, ?)
            """,
            (
                media_id,
                company_id,
            ),
        )

def _get_or_create_company_id(conn, company):
    tmdb_id = company.get("tmdb_id")
    name = company.get("name")

    if tmdb_id is None or not name:
        return None

    conn.execute(
        """
        INSERT INTO companies (
            tmdb_id,
            name
        )
        VALUES (?, ?)
        ON CONFLICT (tmdb_id) DO UPDATE SET
            name = excluded.name
        """,
        (
            tmdb_id,
            name,
        ),
    )

    cursor = conn.execute(
        """
        SELECT id
        FROM companies
        WHERE tmdb_id = ?
        """,
        (tmdb_id,),
    )

    return cursor.fetchone()["id"]

def _save_media_people(conn, media_id, metadata):
    _replace_people_relation(
        conn,
        table_name="media_directors",
        media_id=media_id,
        people=metadata.get("directors", []),
    )
    _replace_people_relation(
        conn,
        table_name="media_creators",
        media_id=media_id,
        people=metadata.get("creators", []),
    )
    _replace_writers_relation(
        conn,
        media_id,
        metadata.get("writers", []),
    )
    _replace_actors_relation(
        conn,
        media_id,
        metadata.get("actors", []),
    )

def _replace_people_relation(conn, table_name, media_id, people):
    conn.execute(
        f"""
        DELETE FROM {table_name}
        WHERE media_id = ?
        """,
        (media_id,),
    )

    for person in people:
        person_id = _get_or_create_person_id(conn, person)

        if person_id is None:
            continue

        conn.execute(
            f"""
            INSERT OR IGNORE INTO {table_name} (
                media_id,
                person_id
            )
            VALUES (?, ?)
            """,
            (
                media_id,
                person_id,
            ),
        )

def _replace_writers_relation(conn, media_id, writers):
    conn.execute(
        """
        DELETE FROM media_writers
        WHERE media_id = ?
        """,
        (media_id,),
    )

    for writer in writers:
        person_id = _get_or_create_person_id(conn, writer)
        job = writer.get("job")

        if person_id is None or not job:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO media_writers (
                media_id,
                person_id,
                job
            )
            VALUES (?, ?, ?)
            """,
            (
                media_id,
                person_id,
                job,
            ),
        )

def _replace_actors_relation(conn, media_id, actors):
    conn.execute(
        """
        DELETE FROM media_actors
        WHERE media_id = ?
        """,
        (media_id,),
    )

    seen_person_ids = set()

    for actor in actors:
        person_id = _get_or_create_person_id(conn, actor)

        if person_id is None or person_id in seen_person_ids:
            continue

        seen_person_ids.add(person_id)

        conn.execute(
            """
            INSERT INTO media_actors (
                media_id,
                person_id,
                character,
                cast_order
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                media_id,
                person_id,
                actor.get("character"),
                actor.get("cast_order"),
            ),
        )

def _get_or_create_person_id(conn, person):
    tmdb_id = person.get("tmdb_id")
    name = person.get("name")

    if tmdb_id is None or not name:
        return None

    conn.execute(
        """
        INSERT INTO people (
            tmdb_id,
            name
        )
        VALUES (?, ?)
        ON CONFLICT (tmdb_id) DO UPDATE SET
            name = excluded.name
        """,
        (
            tmdb_id,
            name,
        ),
    )

    cursor = conn.execute(
        """
        SELECT id
        FROM people
        WHERE tmdb_id = ?
        """,
        (tmdb_id,),
    )

    return cursor.fetchone()["id"]

def _save_media_watch_providers(conn, media_id, watch_providers):
    conn.execute(
        """
        DELETE FROM media_watch_providers
        WHERE media_id = ?
        """,
        (media_id,),
    )

    seen = set()

    for provider in watch_providers:
        if (
            provider.get("provider_tmdb_id") is None
            or not provider.get("provider_name")
            or not provider.get("country_code")
            or not provider.get("access_type")
        ):
            continue

        key = (
            provider["provider_tmdb_id"],
            provider["country_code"],
            provider["access_type"],
        )

        if key in seen:
            continue

        seen.add(key)

        conn.execute(
            """
            INSERT INTO media_watch_providers (
                media_id,
                provider_tmdb_id,
                provider_name,
                country_code,
                access_type
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                media_id,
                provider["provider_tmdb_id"],
                provider["provider_name"],
                provider["country_code"],
                provider["access_type"],
            ),
        )


def _save_media_posters(conn, media_id, metadata, posters):
    posters = _limit_posters(posters, TMDB_MAX_POSTERS_PER_MEDIA)
    posters_checked_at = metadata.get("last_tmdb_posters_checked_at")

    update_media_tmdb_posters_checked_at(conn, media_id, posters_checked_at)

    media_posters = [
        poster
        for poster in posters
        if poster.get("scope", "media") == "media"
    ]
    _replace_media_posters(conn, media_id, media_posters)

    if metadata["media_type"] != "episode":
        return

    episode_details = metadata.get("episode_details") or {}
    series_id = _get_or_create_episode_series_id(conn, episode_details)
    season_num = episode_details.get("season_num")

    if season_num is not None:
        season_posters = [
            poster
            for poster in posters
            if poster.get("scope") == "season"
        ]
        _replace_season_posters(
            conn,
            series_id,
            season_num,
            season_posters,
        )

    series_posters = [
        poster
        for poster in posters
        if poster.get("scope") == "series"
    ]

    if series_posters:
        _replace_media_posters(conn, series_id, series_posters)
        update_media_tmdb_posters_checked_at(conn, series_id, posters_checked_at)

def _limit_posters(posters, limit):
    if limit is None:
        return posters

    if limit < 1:
        return []

    return posters[:limit]

def _replace_media_posters(conn, media_id, posters):
    conn.execute(
        """
        DELETE FROM media_posters
        WHERE media_id = ?
        """,
        (media_id,),
    )

    seen = set()

    for poster in posters:
        if not poster.get("filename"):
            continue

        if poster["filename"] in seen:
            continue

        seen.add(poster["filename"])

        conn.execute(
            """
            INSERT INTO media_posters (
                media_id,
                filename,
                source,
                curation_status,
                is_default
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                media_id,
                poster["filename"],
                poster.get("source") or "other",
                poster.get("curation_status") or "pending",
                _to_db_bool(poster.get("is_default", False)),
            ),
        )

def _replace_season_posters(conn, series_id, season_num, posters):
    conn.execute(
        """
        DELETE FROM season_posters
        WHERE series_id = ?
          AND season_num = ?
        """,
        (
            series_id,
            season_num,
        ),
    )

    seen = set()

    for poster in posters:
        if not poster.get("filename"):
            continue

        if poster["filename"] in seen:
            continue

        seen.add(poster["filename"])

        conn.execute(
            """
            INSERT INTO season_posters (
                series_id,
                season_num,
                filename,
                source,
                curation_status,
                is_default
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                season_num,
                poster["filename"],
                poster.get("source") or "other",
                poster.get("curation_status") or "pending",
                _to_db_bool(poster.get("is_default", False)),
            ),
        )

def _save_media_user_data(conn, media_id, user_data):
    _save_media_state(conn, media_id, user_data)
    watch_history = _prepare_watch_history_for_save(
        conn,
        media_id,
        user_data.get("watch_state"),
        user_data.get("watch_history", []),
    )
    user_data["watch_history"] = watch_history
    _sync_watch_history(conn, media_id, watch_history)
    _sync_media_notes(conn, media_id, user_data.get("notes", []))
    _sync_media_lists(conn, media_id, user_data.get("lists", []))


def _prepare_watch_history_for_save(
    conn,
    media_id,
    requested_watch_state,
    watch_history,
):
    watch_history = list(watch_history or [])

    if watch_history or requested_watch_state != "watched":
        return watch_history

    if _get_media_type(conn, media_id) != "episode":
        return watch_history

    if _get_media_watch_history_ids(conn, media_id):
        return watch_history

    return [{
        "date_earliest": None,
        "date_latest": None,
    }]


def _save_media_state(conn, media_id, user_data):
    watch_state = user_data.get("watch_state")
    impression = user_data.get("impression")
    is_collection_pick = _to_db_bool(user_data.get("is_collection_pick"))
    media_type = _get_media_type(conn, media_id)
    validate_watch_state(media_type, watch_state)

    if watch_state is None and impression is None and is_collection_pick is None:
        conn.execute(
            """
            DELETE FROM media_state
            WHERE media_id = ?
            """,
            (media_id,),
        )
        return

    conn.execute(
        """
        INSERT INTO media_state (
            media_id,
            watch_state,
            impression,
            is_collection_pick
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT (media_id) DO UPDATE SET
            watch_state = excluded.watch_state,
            impression = excluded.impression,
            is_collection_pick = excluded.is_collection_pick,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            media_id,
            watch_state,
            impression,
            is_collection_pick,
        ),
    )


def set_media_watch_state(conn, media_id, watch_state):
    media_type = _get_media_type(conn, media_id)
    validate_watch_state(media_type, watch_state)

    if (
        media_type == "episode"
        and watch_state == "watched"
        and not _get_media_watch_history_ids(conn, media_id)
    ):
        conn.execute(
            """
            INSERT INTO watch_history (
                media_id,
                date_earliest,
                date_latest
            )
            VALUES (?, NULL, NULL)
            """,
            (media_id,),
        )

    if watch_state is None:
        conn.execute(
            """
            UPDATE media_state
            SET
                watch_state = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE media_id = ?
            """,
            (media_id,),
        )
        _delete_empty_media_state(conn, media_id)
        return

    conn.execute(
        """
        INSERT INTO media_state (
            media_id,
            watch_state
        )
        VALUES (?, ?)
        ON CONFLICT (media_id) DO UPDATE SET
            watch_state = excluded.watch_state,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            media_id,
            watch_state,
        ),
    )


def _delete_empty_media_state(conn, media_id):
    conn.execute(
        """
        DELETE FROM media_state
        WHERE media_id = ?
          AND watch_state IS NULL
          AND impression IS NULL
          AND is_collection_pick IS NULL
        """,
        (media_id,),
    )


def _get_media_type(conn, media_id):
    cursor = conn.execute(
        """
        SELECT media_type
        FROM media
        WHERE id = ?
        """,
        (media_id,),
    )
    row = cursor.fetchone()

    if row is None:
        raise ValueError(f"media id {media_id} does not exist.")

    return row["media_type"]


def _sync_episode_watch_state_for_history_transition(
    conn,
    media_id,
    previous_history_ids,
    current_history_ids,
):
    if _get_media_type(conn, media_id) != "episode":
        return

    if current_history_ids - previous_history_ids:
        set_media_watch_state(conn, media_id, "watched")
        return

    if not previous_history_ids or current_history_ids:
        return

    cursor = conn.execute(
        """
        SELECT watch_state
        FROM media_state
        WHERE media_id = ?
        """,
        (media_id,),
    )
    state = cursor.fetchone()

    if state is not None and state["watch_state"] == "watched":
        set_media_watch_state(conn, media_id, None)


def _get_media_watch_history_ids(conn, media_id):
    cursor = conn.execute(
        """
        SELECT id
        FROM watch_history
        WHERE media_id = ?
        """,
        (media_id,),
    )
    return {row["id"] for row in cursor.fetchall()}

def _sync_watch_history(conn, media_id, watch_history):
    previous_history_ids = _get_media_watch_history_ids(conn, media_id)
    kept_ids = []

    for event in watch_history:
        event_id = event.get("id")

        if event_id is None:
            cursor = conn.execute(
                """
                INSERT INTO watch_history (
                    media_id,
                    date_earliest,
                    date_latest
                )
                VALUES (?, ?, ?)
                """,
                (
                    media_id,
                    event.get("date_earliest"),
                    event.get("date_latest"),
                ),
            )
            event["id"] = cursor.lastrowid
            kept_ids.append(event["id"])
            continue

        cursor = conn.execute(
            """
            UPDATE watch_history
            SET
                date_earliest = ?,
                date_latest = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND media_id = ?
            """,
            (
                event.get("date_earliest"),
                event.get("date_latest"),
                event_id,
                media_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(f"watch_history id {event_id} does not belong to media.")

        kept_ids.append(event_id)

    _delete_missing_ids(conn, "watch_history", media_id, kept_ids)
    current_history_ids = _get_media_watch_history_ids(conn, media_id)
    _sync_episode_watch_state_for_history_transition(
        conn,
        media_id,
        previous_history_ids,
        current_history_ids,
    )

def sync_series_episode_watch_history(conn, series_id, episode_watch_history):
    previous_history_ids_by_episode = _get_series_episode_watch_history_ids(
        conn,
        series_id,
    )
    kept_ids = []

    for event in episode_watch_history or []:
        episode_id = _resolve_series_episode_id(conn, series_id, event)
        event_id = event.get("watch_history_id") or event.get("id")

        if event_id is None:
            cursor = conn.execute(
                """
                INSERT INTO watch_history (
                    media_id,
                    date_earliest,
                    date_latest
                )
                VALUES (?, ?, ?)
                """,
                (
                    episode_id,
                    event.get("date_earliest"),
                    event.get("date_latest"),
                ),
            )
            event["episode_id"] = episode_id
            event["series_id"] = series_id
            event["watch_history_id"] = cursor.lastrowid
            kept_ids.append(cursor.lastrowid)
            continue

        cursor = conn.execute(
            """
            UPDATE watch_history
            SET
                date_earliest = ?,
                date_latest = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND media_id = ?
            """,
            (
                event.get("date_earliest"),
                event.get("date_latest"),
                event_id,
                episode_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"watch_history id {event_id} does not belong to episode."
            )

        event["episode_id"] = episode_id
        event["series_id"] = series_id
        kept_ids.append(event_id)

    _delete_missing_series_episode_watch_history(conn, series_id, kept_ids)
    current_history_ids_by_episode = _get_series_episode_watch_history_ids(
        conn,
        series_id,
    )

    for episode_id in (
        previous_history_ids_by_episode.keys()
        | current_history_ids_by_episode.keys()
    ):
        previous_history_ids = previous_history_ids_by_episode.get(episode_id, set())
        current_history_ids = current_history_ids_by_episode.get(episode_id, set())

        if previous_history_ids == current_history_ids:
            continue

        _sync_episode_watch_state_for_history_transition(
            conn,
            episode_id,
            previous_history_ids,
            current_history_ids,
        )


def _get_series_episode_watch_history_ids(conn, series_id):
    cursor = conn.execute(
        """
        SELECT
            ed.media_id AS episode_id,
            wh.id AS watch_history_id
        FROM episode_details ed
        LEFT JOIN watch_history wh
            ON wh.media_id = ed.media_id
        WHERE ed.series_id = ?
        """,
        (series_id,),
    )
    history_ids_by_episode = {}

    for row in cursor.fetchall():
        episode_id = row["episode_id"]
        history_ids_by_episode.setdefault(episode_id, set())

        if row["watch_history_id"] is not None:
            history_ids_by_episode[episode_id].add(row["watch_history_id"])

    return history_ids_by_episode


def _resolve_series_episode_id(conn, series_id, event):
    episode_id = event.get("episode_id")

    if episode_id is not None:
        cursor = conn.execute(
            """
            SELECT media_id
            FROM episode_details
            WHERE series_id = ?
              AND media_id = ?
            """,
            (
                series_id,
                episode_id,
            ),
        )
        row = cursor.fetchone()

        if row is not None:
            return row["media_id"]

    season_num = event.get("season_num")
    episode_num = event.get("episode_num")

    cursor = conn.execute(
        """
        SELECT media_id
        FROM episode_details
        WHERE series_id = ?
          AND season_num = ?
          AND episode_num = ?
        """,
        (
            series_id,
            season_num,
            episode_num,
        ),
    )
    row = cursor.fetchone()

    if row is None:
        raise ValueError(
            "Could not resolve episode "
            f"S{season_num}:E{episode_num} for series {series_id}."
        )

    return row["media_id"]


def _delete_missing_series_episode_watch_history(conn, series_id, kept_ids):
    if kept_ids:
        placeholders = ", ".join("?" for _ in kept_ids)
        conn.execute(
            f"""
            DELETE FROM watch_history
            WHERE media_id IN (
                SELECT media_id
                FROM episode_details
                WHERE series_id = ?
            )
              AND id NOT IN ({placeholders})
            """,
            (series_id, *kept_ids),
        )
        return

    conn.execute(
        """
        DELETE FROM watch_history
        WHERE media_id IN (
            SELECT media_id
            FROM episode_details
            WHERE series_id = ?
        )
        """,
        (series_id,),
    )

def _sync_media_notes(conn, media_id, notes):
    kept_ids = []

    for note in notes:
        note_id = note.get("id")
        note_text = validate_note_text(note.get("note"))

        if note_id is None:
            cursor = conn.execute(
                """
                INSERT INTO media_notes (
                    media_id,
                    note
                )
                VALUES (?, ?)
                """,
                (
                    media_id,
                    note_text,
                ),
            )
            kept_ids.append(cursor.lastrowid)
            continue

        cursor = conn.execute(
            """
            UPDATE media_notes
            SET
                note = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND media_id = ?
            """,
            (
                note_text,
                note_id,
                media_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(f"media_notes id {note_id} does not belong to media.")

        kept_ids.append(note_id)

    _delete_missing_ids(conn, "media_notes", media_id, kept_ids)

def _sync_media_lists(conn, media_id, lists):
    kept_list_ids = []

    for list_item in lists:
        list_id = _get_or_create_list_id(conn, list_item)

        if list_id is None:
            continue

        conn.execute(
            """
            INSERT INTO media_lists (
                media_id,
                list_id
            )
            VALUES (?, ?)
            ON CONFLICT (media_id, list_id) DO NOTHING
            """,
            (
                media_id,
                list_id,
            ),
        )
        kept_list_ids.append(list_id)

    if kept_list_ids:
        placeholders = ", ".join("?" for _ in kept_list_ids)
        conn.execute(
            f"""
            DELETE FROM media_lists
            WHERE media_id = ?
              AND list_id NOT IN ({placeholders})
            """,
            (media_id, *kept_list_ids),
        )
    else:
        conn.execute(
            """
            DELETE FROM media_lists
            WHERE media_id = ?
            """,
            (media_id,),
        )

def _get_or_create_list_id(conn, list_item):
    list_id = list_item.get("id")

    if list_id is not None:
        cursor = conn.execute(
            """
            SELECT id
            FROM lists
            WHERE id = ?
            """,
            (list_id,),
        )

        if cursor.fetchone() is not None:
            return list_id

    name = list_item.get("name")

    if not name:
        if list_id is None:
            return None

        raise ValueError(f"lists id {list_id} does not exist.")

    conn.execute(
        """
        INSERT OR IGNORE INTO lists (
            name
        )
        VALUES (?)
        """,
        (name,),
    )

    cursor = conn.execute(
        """
        SELECT id
        FROM lists
        WHERE name = ?
        """,
        (name,),
    )

    return cursor.fetchone()["id"]

def _delete_missing_ids(conn, table_name, media_id, kept_ids):
    if kept_ids:
        placeholders = ", ".join("?" for _ in kept_ids)
        conn.execute(
            f"""
            DELETE FROM {table_name}
            WHERE media_id = ?
              AND id NOT IN ({placeholders})
            """,
            (media_id, *kept_ids),
        )
    else:
        conn.execute(
            f"""
            DELETE FROM {table_name}
            WHERE media_id = ?
            """,
            (media_id,),
        )


def apply_media_user_changes(conn, media_id, baseline_draft, current_draft):
    """Apply only user-data changes made since ``baseline_draft``.

    The operation is deliberately additive/delta based: rows which were not in
    the baseline are never removed, and persisted rows may only be changed when
    their database value still matches the baseline.  The caller owns the
    surrounding transaction.  Neither draft is mutated.
    """
    media = _validate_existing_draft_identity(
        conn,
        media_id,
        baseline_draft,
        current_draft,
    )
    inserted_ids = {
        "media_watch_history": {},
        "series_episode_watch_history": {},
        "notes": {},
    }
    counts = {
        "state_fields_updated": 0,
        "media_watch_history_inserted": 0,
        "media_watch_history_updated": 0,
        "media_watch_history_deleted": 0,
        "notes_inserted": 0,
        "notes_updated": 0,
        "notes_deleted": 0,
        "lists_added": 0,
        "lists_removed": 0,
        "series_episode_watch_history_inserted": 0,
        "series_episode_watch_history_updated": 0,
        "series_episode_watch_history_deleted": 0,
    }

    baseline_user_data = baseline_draft.get("user_data") or {}
    current_user_data = current_draft.get("user_data") or {}

    counts["state_fields_updated"] = _apply_media_state_field_changes(
        conn,
        media_id,
        media["media_type"],
        baseline_user_data,
        current_user_data,
    )

    baseline_history = baseline_user_data.get("watch_history") or []
    current_history = current_user_data.get("watch_history") or []
    history_result = _empty_owned_delta_result()

    if baseline_history != current_history:
        history_result = _apply_owned_row_delta(
            conn=conn,
            table_name="watch_history",
            media_id=media_id,
            baseline_rows=baseline_history,
            current_rows=current_history,
            value_fields=("date_earliest", "date_latest"),
            id_keys=("id", "watch_history_id"),
            draft_id_namespace="media watch history",
        )
    inserted_ids["media_watch_history"].update(history_result["inserted_ids"])
    counts["media_watch_history_inserted"] = history_result["inserted"]
    counts["media_watch_history_updated"] = history_result["updated"]
    counts["media_watch_history_deleted"] = history_result["deleted"]

    baseline_notes = baseline_user_data.get("notes") or []
    current_notes = current_user_data.get("notes") or []
    note_result = _empty_owned_delta_result()

    if baseline_notes != current_notes:
        for note in current_notes:
            validate_note_text(note.get("note"))

        note_result = _apply_owned_row_delta(
            conn=conn,
            table_name="media_notes",
            media_id=media_id,
            baseline_rows=baseline_notes,
            current_rows=current_notes,
            value_fields=("note",),
            id_keys=("id",),
            draft_id_namespace="media note",
        )
    inserted_ids["notes"].update(note_result["inserted_ids"])
    counts["notes_inserted"] = note_result["inserted"]
    counts["notes_updated"] = note_result["updated"]
    counts["notes_deleted"] = note_result["deleted"]

    baseline_lists = baseline_user_data.get("lists") or []
    current_lists = current_user_data.get("lists") or []
    list_result = {"added": 0, "removed": 0}

    if baseline_lists != current_lists:
        list_result = _apply_media_list_delta(
            conn,
            media_id,
            baseline_lists,
            current_lists,
        )
    counts["lists_added"] = list_result["added"]
    counts["lists_removed"] = list_result["removed"]

    direct_affected_episode_ids = set()
    if media["media_type"] == "episode" and (
        history_result["inserted"] or history_result["deleted"]
    ):
        direct_affected_episode_ids.add(media_id)

    if media["media_type"] == "series":
        baseline_series_view = baseline_draft.get("series_view") or {}
        current_series_view = current_draft.get("series_view") or {}
        baseline_series_history = (
            baseline_series_view.get("episode_watch_history") or []
        )
        current_series_history = (
            current_series_view.get("episode_watch_history") or []
        )
        series_history_result = _empty_series_history_delta_result()

        if baseline_series_history != current_series_history:
            series_history_result = _apply_series_episode_history_delta(
                conn,
                media_id,
                baseline_series_history,
                current_series_history,
            )
        inserted_ids["series_episode_watch_history"].update(
            series_history_result["inserted_ids"]
        )
        counts["series_episode_watch_history_inserted"] = (
            series_history_result["inserted"]
        )
        counts["series_episode_watch_history_updated"] = (
            series_history_result["updated"]
        )
        counts["series_episode_watch_history_deleted"] = (
            series_history_result["deleted"]
        )
        direct_affected_episode_ids.update(
            series_history_result["affected_episode_ids"]
        )

    for episode_id in direct_affected_episode_ids:
        before_ids = history_result["before_ids"] if episode_id == media_id else None
        after_ids = history_result["after_ids"] if episode_id == media_id else None

        if media["media_type"] == "series":
            before_ids = series_history_result["before_ids_by_episode"].get(
                episode_id,
                set(),
            )
            after_ids = series_history_result["after_ids_by_episode"].get(
                episode_id,
                set(),
            )

        _sync_episode_watch_state_for_history_transition(
            conn,
            episode_id,
            before_ids or set(),
            after_ids or set(),
        )

    return {
        "media_id": media_id,
        "inserted_ids_by_draft_id": inserted_ids,
        "counts": counts,
    }


def _empty_owned_delta_result():
    return {
        "inserted_ids": {},
        "inserted": 0,
        "updated": 0,
        "deleted": 0,
        "before_ids": set(),
        "after_ids": set(),
    }


def _empty_series_history_delta_result():
    return {
        "inserted_ids": {},
        "inserted": 0,
        "updated": 0,
        "deleted": 0,
        "affected_episode_ids": set(),
        "before_ids_by_episode": {},
        "after_ids_by_episode": {},
    }


def _validate_existing_draft_identity(
    conn,
    media_id,
    baseline_draft,
    current_draft,
):
    row = conn.execute(
        """
        SELECT id, tmdb_id, media_type
        FROM media
        WHERE id = ?
        """,
        (media_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"media id {media_id} does not exist.")

    for label, draft in (
        ("baseline", baseline_draft),
        ("current", current_draft),
    ):
        draft_media_id = draft.get("media_id")
        metadata = draft.get("metadata") or {}

        if draft_media_id != media_id:
            raise ValueError(
                f"{label} draft media_id does not match media id {media_id}."
            )

        if (
            metadata.get("tmdb_id") != row["tmdb_id"]
            or metadata.get("media_type") != row["media_type"]
        ):
            raise ValueError(
                f"{label} draft identity does not match media id {media_id}."
            )

    return dict(row)


def _normalize_state_value(field, value):
    if field == "is_collection_pick" and value is not None:
        return bool(value)
    return value


def get_media_state(conn, media_id):
    media = conn.execute(
        "SELECT id FROM media WHERE id = ?",
        (media_id,),
    ).fetchone()

    if media is None:
        raise ValueError(f"media id {media_id} does not exist.")

    state = conn.execute(
        """
        SELECT
            watch_state,
            impression,
            is_collection_pick
        FROM media_state
        WHERE media_id = ?
        """,
        (media_id,),
    ).fetchone()

    return {
        "media_id": media_id,
        "watch_state": state["watch_state"] if state is not None else None,
        "impression": state["impression"] if state is not None else None,
        "is_collection_pick": (
            None
            if state is None or state["is_collection_pick"] is None
            else bool(state["is_collection_pick"])
        ),
    }


def apply_media_state_patch(
    conn,
    media_id,
    expected_values,
    changes,
):
    """Patch History-editable state fields with optimistic concurrency checks."""
    editable_fields = ("impression", "is_collection_pick")
    expected_values = dict(expected_values or {})
    changes = dict(changes or {})

    unsupported_fields = set(changes) - set(editable_fields)

    if unsupported_fields:
        unsupported = ", ".join(sorted(unsupported_fields))
        raise ValueError(f"Unsupported media state patch fields: {unsupported}.")

    if not changes:
        return get_media_state(conn, media_id)

    missing_expected_fields = set(changes) - set(expected_values)

    if missing_expected_fields:
        missing = ", ".join(sorted(missing_expected_fields))
        raise ValueError(f"Missing expected media state values: {missing}.")

    for values in (expected_values, changes):
        if "impression" in values and values["impression"] not in {
            None,
            "very_good",
            "good",
            "meh",
            "not_for_me",
            "regret_watching",
        }:
            raise ValueError("Unsupported impression value.")

        if (
            "is_collection_pick" in values
            and values["is_collection_pick"] not in {None, True, False}
        ):
            raise ValueError("Unsupported collection pick value.")

    current_state = get_media_state(conn, media_id)
    normalized_changes = {
        field: _normalize_state_value(field, value)
        for field, value in changes.items()
    }
    normalized_expected = {
        field: _normalize_state_value(field, expected_values[field])
        for field in changes
    }

    fields_to_write = []

    for field, desired_value in normalized_changes.items():
        database_value = current_state[field]

        if database_value == desired_value:
            continue

        if database_value != normalized_expected[field]:
            raise ConcurrentEditError(
                f"media_state.{field} changed before the inline update."
            )

        fields_to_write.append(field)

    if not fields_to_write:
        return current_state

    values_to_write = {
        field: current_state[field]
        for field in ("watch_state", *editable_fields)
    }
    values_to_write.update(normalized_changes)

    state_exists = conn.execute(
        "SELECT 1 FROM media_state WHERE media_id = ?",
        (media_id,),
    ).fetchone() is not None

    if all(value is None for value in values_to_write.values()):
        cursor = conn.execute(
            """
            DELETE FROM media_state
            WHERE media_id = ?
              AND watch_state IS ?
              AND impression IS ?
              AND is_collection_pick IS ?
            """,
            (
                media_id,
                current_state["watch_state"],
                current_state["impression"],
                _to_db_bool(current_state["is_collection_pick"]),
            ),
        )

        if cursor.rowcount == 1:
            return get_media_state(conn, media_id)

        canonical_state = get_media_state(conn, media_id)

        if _state_matches_changes(canonical_state, normalized_changes):
            return canonical_state

        raise ConcurrentEditError(
            "media_state changed before the inline update."
        )

    if not state_exists:
        try:
            conn.execute(
                """
                INSERT INTO media_state (
                    media_id,
                    watch_state,
                    impression,
                    is_collection_pick
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    media_id,
                    values_to_write["watch_state"],
                    values_to_write["impression"],
                    _to_db_bool(values_to_write["is_collection_pick"]),
                ),
            )
        except sqlite3.IntegrityError as exc:
            canonical_state = get_media_state(conn, media_id)

            if _state_matches_changes(canonical_state, normalized_changes):
                return canonical_state

            raise ConcurrentEditError(
                "media_state changed before the inline update."
            ) from exc

        return get_media_state(conn, media_id)

    assignments = ", ".join(f"{field} = ?" for field in fields_to_write)
    parameters = [
        _to_db_bool(normalized_changes[field])
        if field == "is_collection_pick"
        else normalized_changes[field]
        for field in fields_to_write
    ]
    expected_predicates = " AND ".join(
        f"{field} IS ?"
        for field in fields_to_write
    )
    expected_parameters = [
        _to_db_bool(normalized_expected[field])
        if field == "is_collection_pick"
        else normalized_expected[field]
        for field in fields_to_write
    ]
    cursor = conn.execute(
        f"""
        UPDATE media_state
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE media_id = ?
          AND {expected_predicates}
        """,
        (*parameters, media_id, *expected_parameters),
    )
    canonical_state = get_media_state(conn, media_id)

    if cursor.rowcount == 1 or _state_matches_changes(
        canonical_state,
        normalized_changes,
    ):
        return canonical_state

    raise ConcurrentEditError(
        "media_state changed before the inline update."
    )


def _state_matches_changes(state, changes):
    return all(
        state.get(field) == value
        for field, value in changes.items()
    )


def _apply_media_state_field_changes(
    conn,
    media_id,
    media_type,
    baseline_user_data,
    current_user_data,
):
    fields = ("watch_state", "impression", "is_collection_pick")
    state_row = conn.execute(
        """
        SELECT watch_state, impression, is_collection_pick
        FROM media_state
        WHERE media_id = ?
        """,
        (media_id,),
    ).fetchone()
    database_values = {
        field: _normalize_state_value(
            field,
            state_row[field] if state_row is not None else None,
        )
        for field in fields
    }
    values_to_write = dict(database_values)
    changed_fields = []

    for field in fields:
        baseline_value = _normalize_state_value(
            field,
            baseline_user_data.get(field),
        )
        current_value = _normalize_state_value(
            field,
            current_user_data.get(field),
        )

        if current_value == baseline_value:
            continue

        database_value = database_values[field]

        if database_value == current_value:
            continue

        if database_value != baseline_value:
            raise ConcurrentEditError(
                f"media_state.{field} changed after the dialog was opened."
            )

        values_to_write[field] = current_value
        changed_fields.append(field)

    if not changed_fields:
        return 0

    validate_watch_state(media_type, values_to_write["watch_state"])

    if all(values_to_write[field] is None for field in fields):
        conn.execute("DELETE FROM media_state WHERE media_id = ?", (media_id,))
        return len(changed_fields)

    if state_row is None:
        conn.execute(
            """
            INSERT INTO media_state (
                media_id,
                watch_state,
                impression,
                is_collection_pick
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                media_id,
                values_to_write["watch_state"],
                values_to_write["impression"],
                _to_db_bool(values_to_write["is_collection_pick"]),
            ),
        )
        return len(changed_fields)

    assignments = ", ".join(f"{field} = ?" for field in changed_fields)
    parameters = [
        _to_db_bool(values_to_write[field])
        if field == "is_collection_pick"
        else values_to_write[field]
        for field in changed_fields
    ]
    conn.execute(
        f"""
        UPDATE media_state
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE media_id = ?
        """,
        (*parameters, media_id),
    )
    return len(changed_fields)


def _row_persisted_id(row, id_keys):
    for key in id_keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _index_persisted_rows(rows, id_keys, namespace):
    indexed = {}

    for row in rows:
        row_id = _row_persisted_id(row, id_keys)

        if row_id is None:
            continue

        if row_id in indexed:
            raise ValueError(f"Duplicate {namespace} id {row_id}.")

        indexed[row_id] = row

    return indexed


def _canonical_row_values(row, value_fields):
    return tuple(row.get(field) for field in value_fields)


def _fetch_owned_row(conn, table_name, row_id):
    value_columns = {
        "watch_history": "date_earliest, date_latest",
        "media_notes": "note",
    }
    columns = value_columns[table_name]
    return conn.execute(
        f"SELECT id, media_id, {columns} FROM {table_name} WHERE id = ?",
        (row_id,),
    ).fetchone()


def _apply_owned_row_delta(
    *,
    conn,
    table_name,
    media_id,
    baseline_rows,
    current_rows,
    value_fields,
    id_keys,
    draft_id_namespace,
):
    baseline_by_id = _index_persisted_rows(
        baseline_rows,
        id_keys,
        draft_id_namespace,
    )
    current_by_id = _index_persisted_rows(
        current_rows,
        id_keys,
        draft_id_namespace,
    )
    inserted_ids = {}
    inserted = 0
    updated = 0
    deleted = 0
    before_ids = {
        row["id"]
        for row in conn.execute(
            f"SELECT id FROM {table_name} WHERE media_id = ?",
            (media_id,),
        ).fetchall()
    }

    for row_id, baseline_row in baseline_by_id.items():
        database_row = _fetch_owned_row(conn, table_name, row_id)

        if database_row is not None and database_row["media_id"] != media_id:
            raise ValueError(
                f"{draft_id_namespace} id {row_id} does not belong to media."
            )

        baseline_values = _canonical_row_values(baseline_row, value_fields)
        current_row = current_by_id.get(row_id)

        if current_row is None:
            if database_row is None:
                continue

            database_values = tuple(database_row[field] for field in value_fields)

            if database_values != baseline_values:
                raise ConcurrentEditError(
                    f"{draft_id_namespace} id {row_id} changed before deletion."
                )

            conn.execute(
                f"DELETE FROM {table_name} WHERE id = ? AND media_id = ?",
                (row_id, media_id),
            )
            deleted += 1
            continue

        current_values = _canonical_row_values(current_row, value_fields)

        if current_values == baseline_values:
            continue

        if database_row is None:
            raise ConcurrentEditError(
                f"{draft_id_namespace} id {row_id} was deleted concurrently."
            )

        database_values = tuple(database_row[field] for field in value_fields)

        if database_values == current_values:
            continue

        if database_values != baseline_values:
            raise ConcurrentEditError(
                f"{draft_id_namespace} id {row_id} changed concurrently."
            )

        assignments = ", ".join(f"{field} = ?" for field in value_fields)
        conn.execute(
            f"""
            UPDATE {table_name}
            SET {assignments}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND media_id = ?
            """,
            (*current_values, row_id, media_id),
        )
        updated += 1

    for row_id, current_row in current_by_id.items():
        if row_id in baseline_by_id:
            continue

        database_row = _fetch_owned_row(conn, table_name, row_id)

        if database_row is None or database_row["media_id"] != media_id:
            raise ValueError(
                f"{draft_id_namespace} id {row_id} was not part of the baseline."
            )

        if tuple(database_row[field] for field in value_fields) != (
            _canonical_row_values(current_row, value_fields)
        ):
            raise ConcurrentEditError(
                f"{draft_id_namespace} id {row_id} has no editable baseline."
            )

    seen_draft_ids = set()

    for row in current_rows:
        if _row_persisted_id(row, id_keys) is not None:
            continue

        draft_id = row.get("draft_id")

        if not draft_id:
            raise ValueError(f"New {draft_id_namespace} rows require draft_id.")

        if draft_id in seen_draft_ids:
            raise ValueError(f"Duplicate {draft_id_namespace} draft_id {draft_id}.")

        seen_draft_ids.add(draft_id)
        values = _canonical_row_values(row, value_fields)
        columns = ", ".join(("media_id", *value_fields))
        placeholders = ", ".join("?" for _ in range(len(value_fields) + 1))
        cursor = conn.execute(
            f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})",
            (media_id, *values),
        )
        inserted_ids[draft_id] = cursor.lastrowid
        inserted += 1

    after_ids = {
        row["id"]
        for row in conn.execute(
            f"SELECT id FROM {table_name} WHERE media_id = ?",
            (media_id,),
        ).fetchall()
    }
    return {
        "inserted_ids": inserted_ids,
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "before_ids": before_ids,
        "after_ids": after_ids,
    }


def _resolve_list_id_without_renaming(conn, list_item):
    list_id = list_item.get("id")

    if list_id is not None:
        row = conn.execute(
            "SELECT id FROM lists WHERE id = ?",
            (list_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"lists id {list_id} does not exist.")

        return row["id"]

    name = list_item.get("name")

    if not name:
        raise ValueError("A list membership requires id or name.")

    conn.execute("INSERT OR IGNORE INTO lists (name) VALUES (?)", (name,))
    return conn.execute(
        "SELECT id FROM lists WHERE name = ?",
        (name,),
    ).fetchone()["id"]


def _list_ids_for_delta(conn, rows):
    result = set()

    for row in rows:
        result.add(_resolve_list_id_without_renaming(conn, row))

    return result


def _apply_media_list_delta(conn, media_id, baseline_rows, current_rows):
    baseline_ids = _list_ids_for_delta(conn, baseline_rows)
    current_ids = _list_ids_for_delta(conn, current_rows)
    added = 0
    removed = 0

    for list_id in current_ids - baseline_ids:
        cursor = conn.execute(
            """
            INSERT INTO media_lists (media_id, list_id)
            VALUES (?, ?)
            ON CONFLICT (media_id, list_id) DO NOTHING
            """,
            (media_id, list_id),
        )
        added += max(cursor.rowcount, 0)

    for list_id in baseline_ids - current_ids:
        cursor = conn.execute(
            "DELETE FROM media_lists WHERE media_id = ? AND list_id = ?",
            (media_id, list_id),
        )
        removed += max(cursor.rowcount, 0)

    return {"added": added, "removed": removed}


def _series_history_database_row(conn, history_id):
    return conn.execute(
        """
        SELECT
            wh.id,
            wh.media_id AS episode_id,
            wh.date_earliest,
            wh.date_latest,
            ed.series_id,
            ed.season_num,
            ed.episode_num
        FROM watch_history wh
        LEFT JOIN episode_details ed
            ON ed.media_id = wh.media_id
        WHERE wh.id = ?
        """,
        (history_id,),
    ).fetchone()


def _canonical_series_history_values(conn, series_id, row):
    episode_id = _resolve_delta_series_episode_id(conn, series_id, row)
    return (
        episode_id,
        row.get("date_earliest"),
        row.get("date_latest"),
    )


def _resolve_delta_series_episode_id(conn, series_id, event):
    episode_id = event.get("episode_id")
    tmdb_id = event.get("tmdb_id")

    if episode_id is not None:
        row = conn.execute(
            """
            SELECT e.id, e.tmdb_id
            FROM episode_details ed
            JOIN media e ON e.id = ed.media_id
            WHERE ed.series_id = ? AND e.id = ?
            """,
            (series_id, episode_id),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"episode id {episode_id} does not belong to series {series_id}."
            )

        if tmdb_id is not None and tmdb_id != row["tmdb_id"]:
            raise ValueError(
                f"episode id {episode_id} does not match TMDB id {tmdb_id}."
            )

        return row["id"]

    if tmdb_id is not None:
        row = conn.execute(
            """
            SELECT e.id
            FROM episode_details ed
            JOIN media e ON e.id = ed.media_id
            WHERE ed.series_id = ?
              AND e.tmdb_id = ?
              AND e.media_type = 'episode'
            """,
            (series_id, tmdb_id),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"episode TMDB id {tmdb_id} does not belong to series {series_id}."
            )

        return row["id"]

    return _resolve_series_episode_id(conn, series_id, event)


def _database_series_history_values(row):
    return (
        row["episode_id"],
        row["date_earliest"],
        row["date_latest"],
    )


def _series_history_ids_by_episode(conn, series_id):
    result = {}
    rows = conn.execute(
        """
        SELECT wh.id, wh.media_id AS episode_id
        FROM watch_history wh
        JOIN episode_details ed
            ON ed.media_id = wh.media_id
        WHERE ed.series_id = ?
        """,
        (series_id,),
    ).fetchall()

    for row in rows:
        result.setdefault(row["episode_id"], set()).add(row["id"])

    return result


def _apply_series_episode_history_delta(
    conn,
    series_id,
    baseline_rows,
    current_rows,
):
    id_keys = ("watch_history_id", "id")
    baseline_by_id = _index_persisted_rows(
        baseline_rows,
        id_keys,
        "series episode watch history",
    )
    current_by_id = _index_persisted_rows(
        current_rows,
        id_keys,
        "series episode watch history",
    )
    before_ids_by_episode = _series_history_ids_by_episode(conn, series_id)
    inserted_ids = {}
    inserted = 0
    updated = 0
    deleted = 0
    affected_episode_ids = set()

    for history_id, baseline_row in baseline_by_id.items():
        database_row = _series_history_database_row(conn, history_id)

        if database_row is not None and database_row["series_id"] != series_id:
            raise ValueError(
                "watch_history id "
                f"{history_id} does not belong to series {series_id}."
            )

        baseline_values = _canonical_series_history_values(
            conn,
            series_id,
            baseline_row,
        )
        current_row = current_by_id.get(history_id)

        if current_row is None:
            if database_row is None:
                continue

            if _database_series_history_values(database_row) != baseline_values:
                raise ConcurrentEditError(
                    "series episode watch history id "
                    f"{history_id} changed before deletion."
                )

            conn.execute(
                "DELETE FROM watch_history WHERE id = ? AND media_id = ?",
                (history_id, database_row["episode_id"]),
            )
            affected_episode_ids.add(database_row["episode_id"])
            deleted += 1
            continue

        current_values = _canonical_series_history_values(
            conn,
            series_id,
            current_row,
        )

        if current_values == baseline_values:
            continue

        if database_row is None:
            raise ConcurrentEditError(
                f"series episode watch history id {history_id} was deleted."
            )

        database_values = _database_series_history_values(database_row)

        if database_values == current_values:
            continue

        if database_values != baseline_values:
            raise ConcurrentEditError(
                f"series episode watch history id {history_id} changed concurrently."
            )

        conn.execute(
            """
            UPDATE watch_history
            SET
                media_id = ?,
                date_earliest = ?,
                date_latest = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (*current_values, history_id),
        )
        if baseline_values[0] != current_values[0]:
            affected_episode_ids.update((baseline_values[0], current_values[0]))
        updated += 1

    for history_id, current_row in current_by_id.items():
        if history_id in baseline_by_id:
            continue

        database_row = _series_history_database_row(conn, history_id)

        if database_row is None or database_row["series_id"] != series_id:
            raise ValueError(
                "series episode watch history id "
                f"{history_id} was not part of the baseline."
            )

        if _database_series_history_values(database_row) != (
            _canonical_series_history_values(conn, series_id, current_row)
        ):
            raise ConcurrentEditError(
                "series episode watch history id "
                f"{history_id} has no editable baseline."
            )

    seen_draft_ids = set()

    for row in current_rows:
        if _row_persisted_id(row, id_keys) is not None:
            continue

        draft_id = row.get("draft_id")

        if not draft_id:
            raise ValueError(
                "New series episode watch history rows require draft_id."
            )

        if draft_id in seen_draft_ids:
            raise ValueError(
                "Duplicate series episode watch history "
                f"draft_id {draft_id}."
            )

        seen_draft_ids.add(draft_id)
        episode_id, date_earliest, date_latest = (
            _canonical_series_history_values(conn, series_id, row)
        )
        cursor = conn.execute(
            """
            INSERT INTO watch_history (media_id, date_earliest, date_latest)
            VALUES (?, ?, ?)
            """,
            (episode_id, date_earliest, date_latest),
        )
        inserted_ids[draft_id] = cursor.lastrowid
        affected_episode_ids.add(episode_id)
        inserted += 1

    after_ids_by_episode = _series_history_ids_by_episode(conn, series_id)
    return {
        "inserted_ids": inserted_ids,
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "affected_episode_ids": affected_episode_ids,
        "before_ids_by_episode": before_ids_by_episode,
        "after_ids_by_episode": after_ids_by_episode,
    }


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

def _to_db_bool(value):
    if value is None:
        return None

    return 1 if value else 0
