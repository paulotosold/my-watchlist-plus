def get_media_by_imdb_id(conn, imdb_id):
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
            runtime_min
        FROM media
        WHERE imdb_id = ?
        """,
        (imdb_id,),
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
            total_runtime_min
        FROM series_summary
        WHERE series_id = ?
        """,
        (media_id,),
    )

    row = cursor.fetchone()

    if row is None:
        return None

    return dict(row)

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

        "genres": get_db_genres(conn, media_id),
        "spoken_languages": get_db_spoken_languages(conn, media_id),
        "origin_language": get_db_origin_language(conn, media_id),
        "production_countries": get_db_production_countries(conn, media_id),
        "production_companies": get_db_production_companies(conn, media_id),
        "directors": get_db_directors(conn, media_id),
        "creators": get_db_creators(conn, media_id),
        "writers": get_db_writers(conn, media_id),
        "actors": get_db_actors(conn, media_id),

        "series_summary": get_db_series_summary(conn, media_id) if media_type == "series" else None,
        "episode_details": get_db_episode_details(conn, media_id) if media_type == "episode" else None,
    }

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

def get_db_media_user_data(conn, metadata):
    pass



########################################################
def find_metadata_by_tmdb_id(conn, tmdb_infos, user_prefs):
    pass


def add_media(conn, tmdb_infos, user_prefs):
    media_type = tmdb_infos["media_type"]

    if media_type == "movie":
        return add_movie(conn, tmdb_infos, user_prefs)

    if media_type == "series":
        return add_series(conn, tmdb_infos, user_prefs)

    if media_type == "episode":
        return add_episode(conn, tmdb_infos, user_prefs)

    raise ValueError(f"Unsupported media_type: {media_type}")

def add_movie(conn, tmdb_infos, user_prefs):
    return

def add_series(conn, tmdb_infos, user_prefs):
    return

def add_episode(conn, tmdb_infos, user_prefs):
    return
