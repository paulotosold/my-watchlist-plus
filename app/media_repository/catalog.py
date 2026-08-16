"""Persist shared media catalog metadata, providers, and posters."""

from app.config import TMDB_MAX_POSTERS_PER_MEDIA

from .queries import _get_db_media_id
from .errors import ConcurrentEditError
from .queries import get_direct_media_posters
from .user_data import (
    _save_media_user_data,
    _to_db_bool,
    get_empty_media_user_data,
)


TMDB_FRESHNESS_COLUMNS = (
    "last_tmdb_metadata_checked_at",
    "last_tmdb_posters_checked_at",
    "last_tmdb_watch_providers_checked_at",
)

def replace_media_watch_providers(conn, media_id, watch_providers, checked_at=None):
    _save_media_watch_providers(conn, media_id, watch_providers)
    update_media_tmdb_watch_providers_checked_at(
        conn,
        media_id,
        checked_at,
    )


def replace_media_posters(
    conn,
    media_id,
    posters,
    *,
    expected_posters=None,
    checked_at=None,
):
    """Replace direct poster selections with optimistic concurrency."""
    owner = conn.execute(
        "SELECT 1 FROM media WHERE id = ?",
        (media_id,),
    ).fetchone()
    if owner is None:
        raise ValueError(f"media id {media_id} does not exist.")

    current = get_direct_media_posters(conn, media_id)
    if (
        expected_posters is not None
        and _poster_signature(current) != _poster_signature(expected_posters)
    ):
        raise ConcurrentEditError(
            "Posters changed in another window. Reopen Media Details and try again."
        )

    normalized = []
    seen = set()
    default_count = 0
    for raw_poster in posters or []:
        filename = _validate_poster_filename(raw_poster.get("filename"))
        if filename in seen:
            continue
        seen.add(filename)
        source = raw_poster.get("source") or "other"
        if source not in {"tmdb", "user", "other"}:
            raise ValueError("Poster source is invalid.")
        is_default = bool(raw_poster.get("is_default", False))
        default_count += int(is_default)
        normalized.append({
            "filename": filename,
            "source": source,
            "curation_status": "selected",
            "is_default": is_default,
        })

    if default_count > 1:
        raise ValueError("Only one poster can be the default.")

    _replace_media_posters(conn, media_id, normalized)
    update_media_tmdb_posters_checked_at(conn, media_id, checked_at)
    return normalized


def poster_filename_is_referenced(conn, filename):
    filename = _validate_poster_filename(filename)
    row = conn.execute(
        """
        SELECT 1 FROM media_posters WHERE filename = ?
        UNION ALL
        SELECT 1 FROM season_posters WHERE filename = ?
        LIMIT 1
        """,
        (filename, filename),
    ).fetchone()
    return row is not None


def _poster_signature(posters):
    return sorted(
        (
            str(poster.get("filename") or "").lstrip("/"),
            poster.get("source") or "other",
            poster.get("curation_status") or "pending",
            bool(poster.get("is_default", False)),
        )
        for poster in posters or []
        if poster.get("filename")
    )


def _validate_poster_filename(filename):
    filename = str(filename or "").strip().lstrip("/")
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise ValueError("Poster filename must be a simple filename.")
    return filename

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

    posters_checked_at = (
        metadata.get("last_tmdb_posters_checked_at")
        if metadata["media_type"] != "episode"
        else None
    )

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
            posters_checked_at,
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

def insert_missing_series_season_posters(conn, series_id, season_posters):
    if (
        not isinstance(series_id, int)
        or isinstance(series_id, bool)
        or series_id < 1
    ):
        raise ValueError("series_id must reference a series.")

    owner = conn.execute(
        "SELECT media_type FROM media WHERE id = ?",
        (series_id,),
    ).fetchone()

    if owner is None or owner["media_type"] != "series":
        raise ValueError("series_id must reference a series.")

    season_posters = list(season_posters or [])

    if not season_posters:
        return 0

    posters_by_season = {}

    for poster in season_posters:
        if not isinstance(poster, dict):
            raise ValueError("Each season poster must be a dictionary.")

        if poster.get("scope") != "season":
            raise ValueError("Season poster scope must be 'season'.")

        season_num = poster.get("season_num")

        if (
            not isinstance(season_num, int)
            or isinstance(season_num, bool)
            or season_num < 1
        ):
            raise ValueError("Season poster season_num must be a positive integer.")

        filename = poster.get("filename")

        if (
            not isinstance(filename, str)
            or not filename.strip()
            or filename != filename.strip()
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
        ):
            raise ValueError("Season poster filename must be a simple filename.")

        source = poster.get("source") or "other"
        curation_status = poster.get("curation_status") or "pending"
        is_default = poster.get("is_default", False)

        if source not in {"tmdb", "user", "other"}:
            raise ValueError("Season poster source is invalid.")

        if curation_status not in {
            "pending",
            "selected",
            "discarded",
            "failed",
        }:
            raise ValueError("Season poster curation_status is invalid.")

        if not isinstance(is_default, bool):
            raise ValueError("Season poster is_default must be a boolean.")

        if is_default and curation_status != "selected":
            raise ValueError(
                "A default season poster must have selected status."
            )

        posters_by_season.setdefault(season_num, {
            **poster,
            "source": source,
            "curation_status": curation_status,
            "is_default": is_default,
        })

    inserted_count = 0

    for season_num, poster in posters_by_season.items():
        cursor = conn.execute(
            """
            INSERT INTO season_posters (
                series_id,
                season_num,
                filename,
                source,
                curation_status,
                is_default
            )
            SELECT ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1
                FROM season_posters
                WHERE series_id = ?
                  AND season_num = ?
            )
            """,
            (
                series_id,
                season_num,
                poster["filename"],
                poster.get("source") or "other",
                poster.get("curation_status") or "pending",
                _to_db_bool(poster.get("is_default", False)),
                series_id,
                season_num,
            ),
        )
        inserted_count += cursor.rowcount

    return inserted_count

def _save_media_posters(conn, media_id, metadata, posters):
    posters = _limit_posters(posters, TMDB_MAX_POSTERS_PER_MEDIA)
    posters_checked_at = metadata.get("last_tmdb_posters_checked_at")

    if metadata["media_type"] != "episode":
        update_media_tmdb_posters_checked_at(conn, media_id, posters_checked_at)

    media_posters = [
        poster
        for poster in posters
        if poster.get("scope", "media") == "media"
    ]

    if media_posters:
        _insert_media_posters_if_missing(conn, media_id, media_posters)

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

        if season_posters:
            insert_missing_series_season_posters(
                conn,
                series_id,
                season_posters,
            )

    series_posters = [
        poster
        for poster in posters
        if poster.get("scope") == "series"
    ]

    if series_posters:
        _insert_media_posters_if_missing(conn, series_id, series_posters)

def _limit_posters(posters, limit):
    explicitly_selected = [
        poster
        for poster in posters
        if poster.get("curation_status") == "selected"
    ]
    if explicitly_selected:
        return explicitly_selected

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

def _insert_media_posters_if_missing(conn, media_id, posters):
    existing_poster = conn.execute(
        "SELECT 1 FROM media_posters WHERE media_id = ? LIMIT 1",
        (media_id,),
    ).fetchone()

    if existing_poster is not None:
        return

    _replace_media_posters(conn, media_id, posters)

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
