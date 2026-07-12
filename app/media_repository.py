from app.config import TMDB_MAX_POSTERS_PER_MEDIA
from app.watch_states import validate_watch_state


TMDB_FRESHNESS_COLUMNS = (
    "last_tmdb_metadata_checked_at",
    "last_tmdb_posters_checked_at",
    "last_tmdb_watch_providers_checked_at",
)


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
        ORDER BY l.name
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
        ORDER BY name
        """
    )

    return [dict(row) for row in cursor.fetchall()]


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
        note_text = note.get("note") or ""

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

def _to_db_bool(value):
    if value is None:
        return None

    return 1 if value else 0
