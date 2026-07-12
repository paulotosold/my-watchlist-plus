from copy import deepcopy
import re

from app.media_draft_builder import build_media_draft_from_db
from app.watch_states import VALID_WATCH_STATES_BY_MEDIA_TYPE
from db.connection import get_connection


DEFAULT_SEARCH_INTENT = {
    "watch_state": {
        "include": ["to_watch"],
    },
    "order_by": [
        {"field": "random"},
    ],
}

ALLOWED_WATCH_STATES = frozenset().union(
    *VALID_WATCH_STATES_BY_MEDIA_TYPE.values()
)

ALLOWED_ORDER_FIELDS = {
    "media_id": "m.id",
    "random": "RANDOM()",
    "title": "m.title",
    "release_date": "m.release_date",
}

EPISODE_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])s0*(\d+)e0*(\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


class FilteredMedia:
    def __init__(self, search_intent=None):
        self.search_intent = deepcopy(search_intent or DEFAULT_SEARCH_INTENT)
        self.filter_parameters = self.search_intent
        self.media_list = []
        self.next_media_index = 0

    def refresh(self):
        with get_connection() as conn:
            rows = get_media_rows_for_search(conn, self.search_intent)
            self.media_list = []

            for row in rows:
                media_draft = build_media_draft_from_db(conn, row)

                if "resolved_watch_state" in row.keys():
                    media_draft.setdefault("user_data", {})["watch_state"] = (
                        row["resolved_watch_state"]
                    )

                self.media_list.append(media_draft)

        self.next_media_index = 0
        return self.media_list


def get_media_rows_for_search(conn, search_intent):
    query, params = build_media_search_query(search_intent)
    cursor = conn.execute(query, params)
    return cursor.fetchall()


def build_media_search_query(search_intent):
    library_query = str(search_intent.get("library_query") or "").strip()

    if library_query:
        return _build_library_search_query(library_query, search_intent)

    statuses = _get_included_watch_states(search_intent)
    placeholders = ", ".join("?" for _ in statuses)
    params = list(statuses)

    where_clauses = [
        f"ms.watch_state IN ({placeholders})",
    ]

    where_sql = "\n          AND ".join(where_clauses)
    order_sql = _build_order_by(search_intent)

    query = f"""
        SELECT
            m.id,
            m.tmdb_id,
            m.imdb_id,
            m.media_type,
            m.title,
            m.original_title,
            m.production_status,
            m.release_date,
            m.runtime_min,
            m.last_tmdb_metadata_checked_at,
            m.last_tmdb_posters_checked_at,
            m.last_tmdb_watch_providers_checked_at,
            ms.watch_state AS resolved_watch_state
        FROM media m
        JOIN media_state ms
            ON ms.media_id = m.id
        WHERE {where_sql}
        {order_sql}
    """

    return query, params


def _build_library_search_query(library_query, search_intent):
    episode_match = EPISODE_CODE_PATTERN.search(library_query)
    text_query = library_query
    where_clauses = []
    params = []

    if episode_match is not None:
        season_num = int(episode_match.group(1))
        episode_num = int(episode_match.group(2))
        text_query = (
            library_query[:episode_match.start()]
            + " "
            + library_query[episode_match.end():]
        )
        where_clauses.append(
            """
            m.media_type = 'episode'
            AND ed.season_num = ?
            AND ed.episode_num = ?
            """
        )
        params.extend((season_num, episode_num))

    text_query = " ".join(text_query.split())

    if text_query:
        title_pattern = _build_like_pattern(text_query)
        where_clauses.append(
            """
            (
                LOWER(m.title) LIKE ? ESCAPE '\\'
                OR LOWER(COALESCE(m.original_title, '')) LIKE ? ESCAPE '\\'
                OR LOWER(COALESCE(parent_series.title, '')) LIKE ? ESCAPE '\\'
                OR LOWER(COALESCE(parent_series.original_title, '')) LIKE ? ESCAPE '\\'
                OR LOWER(
                    COALESCE(parent_series.title, '') || ' ' || m.title
                ) LIKE ? ESCAPE '\\'
                OR LOWER(
                    COALESCE(parent_series.original_title, '') || ' '
                    || COALESCE(m.original_title, '')
                ) LIKE ? ESCAPE '\\'
            )
            """
        )
        params.extend([title_pattern] * 6)

    where_sql = "\n          AND ".join(where_clauses)
    order_sql = _build_order_by(
        {
            **search_intent,
            "order_by": search_intent.get("order_by") or [{"field": "title"}],
        }
    )

    query = f"""
        SELECT
            m.id,
            m.tmdb_id,
            m.imdb_id,
            m.media_type,
            m.title,
            m.original_title,
            m.production_status,
            m.release_date,
            m.runtime_min,
            m.last_tmdb_metadata_checked_at,
            m.last_tmdb_posters_checked_at,
            m.last_tmdb_watch_providers_checked_at,
            ms.watch_state AS resolved_watch_state
        FROM media m
        LEFT JOIN media_state ms
            ON ms.media_id = m.id
        LEFT JOIN episode_details ed
            ON ed.media_id = m.id
        LEFT JOIN media parent_series
            ON parent_series.id = ed.series_id
           AND parent_series.media_type = 'series'
        WHERE {where_sql}
        {order_sql}
    """

    return query, params


def _build_like_pattern(value):
    escaped = str(value).lower()
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%")
    escaped = escaped.replace("_", "\\_")
    return f"%{escaped}%"


def _get_included_watch_states(search_intent):
    watch_state = search_intent.get("watch_state") or {}
    statuses = watch_state.get("include") or []

    if not statuses:
        raise ValueError("search_intent.watch_state.include must not be empty.")

    unknown_statuses = sorted(set(statuses) - ALLOWED_WATCH_STATES)

    if unknown_statuses:
        raise ValueError(f"Unsupported watch states: {unknown_statuses}")

    return statuses


def _build_order_by(search_intent):
    order_by = search_intent.get("order_by") or [{"field": "random"}]
    clauses = []

    for order_item in order_by:
        field = order_item.get("field")

        if field not in ALLOWED_ORDER_FIELDS:
            raise ValueError(f"Unsupported order field: {field}")

        expression = ALLOWED_ORDER_FIELDS[field]

        if field == "random":
            clauses.append(expression)
            continue

        direction = str(order_item.get("direction", "asc")).lower()

        if direction not in {"asc", "desc"}:
            raise ValueError(f"Unsupported order direction: {direction}")

        clauses.append(f"{expression} {direction.upper()}")

    return "ORDER BY " + ", ".join(clauses)
