from copy import deepcopy

from app.media_draft_builder import build_media_draft_from_db
from db.connection import get_connection


DEFAULT_SEARCH_INTENT = {
    "watch_state": {
        "include": ["suggested", "to_watch", "watching"],
    },
    "hide_to_watch_episodes_when_series_included": True,
    "order_by": [
        {"field": "random"},
    ],
}

ALLOWED_WATCH_STATES = {
    "suggested",
    "to_watch",
    "watched",
    "watching",
    "not_interested",
    "dropped",
}

ALLOWED_ORDER_FIELDS = {
    "media_id": "m.id",
    "random": "RANDOM()",
    "title": "m.title",
    "release_date": "m.release_date",
}


class FilteredMedia:
    def __init__(self, search_intent=None):
        self.search_intent = deepcopy(search_intent or DEFAULT_SEARCH_INTENT)
        self.filter_parameters = self.search_intent
        self.media_list = []
        self.next_media_index = 0

    def refresh(self):
        with get_connection() as conn:
            rows = get_media_rows_for_search(conn, self.search_intent)
            self.media_list = [
                build_media_draft_from_db(conn, row)
                for row in rows
            ]

        self.next_media_index = 0
        return self.media_list


def get_media_rows_for_search(conn, search_intent):
    query, params = build_media_search_query(search_intent)
    cursor = conn.execute(query, params)
    return cursor.fetchall()


def build_media_search_query(search_intent):
    statuses = _get_included_watch_states(search_intent)
    placeholders = ", ".join("?" for _ in statuses)
    params = list(statuses)

    where_clauses = [
        f"ms.watch_state IN ({placeholders})",
    ]

    if search_intent.get("hide_to_watch_episodes_when_series_included", False):
        series_placeholders = ", ".join("?" for _ in statuses)
        where_clauses.append(
            f"""
            NOT (
                m.media_type = 'episode'
                AND ms.watch_state = 'to_watch'
                AND series_ms.watch_state IN ({series_placeholders})
            )
            """
        )
        params.extend(statuses)

    elif search_intent.get("hide_to_watch_episodes_when_series_watching", False):
        where_clauses.append(
            """
            NOT (
                m.media_type = 'episode'
                AND ms.watch_state = 'to_watch'
                AND series_ms.watch_state = 'watching'
            )
            """
        )

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
            m.runtime_min
        FROM media m
        JOIN media_state ms
            ON ms.media_id = m.id
        LEFT JOIN episode_details ed
            ON ed.media_id = m.id
        LEFT JOIN media_state series_ms
            ON series_ms.media_id = ed.series_id
        WHERE {where_sql}
        {order_sql}
    """

    return query, params


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
