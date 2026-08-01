"""Exact, multilingual title matching for lightweight media candidates."""

from __future__ import annotations

import app.media_repository as media_repo
import app.tmdb_fetcher as tmdb_fetcher


SUPPORTED_MEDIA_TYPES = {"movie", "series"}
_TITLE_SEPARATOR_TRANSLATION = str.maketrans({
    character: " "
    for character in ":-\u2010\u2011\u2012\u2013\u2014\u2015"
})


def normalize_title(value) -> str:
    """Normalize only the separators intentionally ignored by exact matching."""
    if value is None:
        return ""

    normalized = str(value).casefold().translate(_TITLE_SEPARATOR_TRANSLATION)
    return " ".join(normalized.split())


def find_local_title_matches(conn, query) -> list[dict]:
    """Return movie/series rows whose title or original title matches exactly."""
    normalized_query = normalize_title(query)

    if not normalized_query:
        return []

    rows = conn.execute(
        """
        SELECT
            m.id,
            m.tmdb_id,
            m.imdb_id,
            m.media_type,
            m.title,
            m.original_title,
            m.release_date,
            (
                SELECT mp.filename
                FROM media_posters mp
                WHERE mp.media_id = m.id
                  AND mp.curation_status IN ('selected', 'pending')
                ORDER BY
                    mp.is_default DESC,
                    CASE mp.curation_status
                        WHEN 'selected' THEN 1
                        WHEN 'pending' THEN 2
                        ELSE 3
                    END,
                    mp.filename
                LIMIT 1
            ) AS poster_path
        FROM media m
        WHERE m.media_type IN ('movie', 'series')
        ORDER BY m.id
        """
    ).fetchall()

    matches = []

    for row in rows:
        if normalized_query not in {
            normalize_title(row["title"]),
            normalize_title(row["original_title"]),
        }:
            continue

        matches.append(_db_candidate_from_row(row))

    return matches


def find_tmdb_title_matches(query) -> list[dict]:
    """Retain exact default, original, localized, or alternate TMDB titles."""
    normalized_query = normalize_title(query)

    if not normalized_query:
        return []

    candidates = tmdb_fetcher.search_tmdb_title_candidates(str(query).strip())
    return filter_exact_tmdb_title_matches(candidates, normalized_query)


def filter_exact_tmdb_title_matches(candidates, query) -> list[dict]:
    """Filter already-fetched TMDB candidates while preserving their order."""
    normalized_query = normalize_title(query)

    if not normalized_query:
        return []

    matches = []

    for candidate in candidates or []:
        if candidate.get("media_type") not in SUPPORTED_MEDIA_TYPES:
            continue

        candidate_titles = [
            candidate.get("title"),
            candidate.get("original_title"),
            *(candidate.get("localized_titles") or []),
            *(candidate.get("alternate_titles") or []),
        ]

        if not any(
            normalize_title(title) == normalized_query
            for title in candidate_titles
            if title is not None
        ):
            continue

        matches.append(candidate)

    return matches


def merge_title_matches(conn, local_matches, tmdb_matches) -> list[dict]:
    """Merge matches by TMDB identity, preferring DB data and TMDB ordering."""
    local_matches = list(local_matches or [])
    tmdb_matches = list(tmdb_matches or [])
    local_by_identity = {
        _candidate_identity(candidate): candidate
        for candidate in local_matches
        if _candidate_identity(candidate) is not None
    }
    merged = []
    seen = set()

    for tmdb_candidate in tmdb_matches:
        identity = _candidate_identity(tmdb_candidate)

        if identity is None or identity in seen:
            continue

        media_type, tmdb_id = identity
        media_from_db = media_repo.get_media_by_tmdb_id(
            conn,
            tmdb_id,
            media_type,
        )

        if media_from_db is not None:
            candidate = local_by_identity.get(identity)

            if candidate is None:
                candidate = _db_candidate_from_media(conn, media_from_db)

            candidate = dict(candidate)
            remote_poster_path = tmdb_candidate.get("poster_path")

            if remote_poster_path:
                candidate["remote_poster_path"] = remote_poster_path
        else:
            candidate = tmdb_candidate

        merged.append(candidate)
        seen.add(identity)

    for candidate in sorted(
        local_matches,
        key=lambda item: (
            item.get("media_id") is None,
            item.get("media_id") if item.get("media_id") is not None else 0,
        ),
    ):
        identity = _candidate_identity(candidate)

        if identity is None or identity in seen:
            continue

        merged.append(candidate)
        seen.add(identity)

    return merged


def find_exact_title_matches(conn, query) -> list[dict]:
    """Run local and TMDB exact-title lookup, then return merged candidates.

    TMDB exceptions intentionally propagate. Callers that need to continue with
    local matches after a technical failure can invoke the three public stages
    separately.
    """
    local_matches = find_local_title_matches(conn, query)
    tmdb_matches = find_tmdb_title_matches(query)
    return merge_title_matches(conn, local_matches, tmdb_matches)


def _candidate_identity(candidate):
    media_type = candidate.get("media_type")
    tmdb_id = candidate.get("tmdb_id")

    if media_type not in SUPPORTED_MEDIA_TYPES or tmdb_id is None:
        return None

    return media_type, tmdb_id


def _db_candidate_from_media(conn, media_from_db):
    poster_row = conn.execute(
        """
        SELECT filename
        FROM media_posters
        WHERE media_id = ?
          AND curation_status IN ('selected', 'pending')
        ORDER BY
            is_default DESC,
            CASE curation_status
                WHEN 'selected' THEN 1
                WHEN 'pending' THEN 2
                ELSE 3
            END,
            filename
        LIMIT 1
        """,
        (media_from_db["id"],),
    ).fetchone()
    poster_path = poster_row["filename"] if poster_row is not None else None

    return {
        "source": "db",
        "media_id": media_from_db["id"],
        "media_type": media_from_db["media_type"],
        "tmdb_id": media_from_db["tmdb_id"],
        "imdb_id": media_from_db.get("imdb_id"),
        "title": media_from_db["title"],
        "original_title": media_from_db.get("original_title"),
        "localized_titles": [],
        "alternate_titles": [],
        "release_date": media_from_db.get("release_date"),
        "poster_path": poster_path,
    }


def _db_candidate_from_row(row):
    return {
        "source": "db",
        "media_id": row["id"],
        "media_type": row["media_type"],
        "tmdb_id": row["tmdb_id"],
        "imdb_id": row["imdb_id"],
        "title": row["title"],
        "original_title": row["original_title"],
        "localized_titles": [],
        "alternate_titles": [],
        "release_date": row["release_date"],
        "poster_path": row["poster_path"],
    }
