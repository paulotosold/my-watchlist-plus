"""Persist user-owned media state, history, notes, and lists."""

import sqlite3

from app.media_user_data.lists import (
    DUPLICATE_LIST_NAME_ERROR,
    normalize_list_description,
    validate_list_name,
)
from app.media_user_data.notes import validate_note_text
from app.media_user_data.watch_states import validate_watch_state

from .errors import ConcurrentEditError
from .queries import _get_db_media_id

def get_empty_media_user_data():
    return {
        "watch_state": None,
        "impression": None,
        "is_cabinet_worthy": None,
        "cabinet_order": None,
        "watch_history": [],
        "notes": [],
        "lists": [],
    }

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
            is_cabinet_worthy,
            cabinet_order
        FROM media_state
        WHERE media_id = ?
        """,
        (media_id,),
    )

    state = cursor.fetchone()

    if state is not None:
        user_data["watch_state"] = state["watch_state"]
        user_data["impression"] = state["impression"]
        user_data["is_cabinet_worthy"] = (
            None
            if state["is_cabinet_worthy"] is None
            else bool(state["is_cabinet_worthy"])
        )
        user_data["cabinet_order"] = state["cabinet_order"]

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
    is_cabinet_worthy = _to_db_bool(user_data.get("is_cabinet_worthy"))
    media_type = _get_media_type(conn, media_id)
    validate_watch_state(media_type, watch_state)

    previous_state = conn.execute(
        """
        SELECT is_cabinet_worthy, cabinet_order
        FROM media_state
        WHERE media_id = ?
        """,
        (media_id,),
    ).fetchone()
    previous_is_cabinet_worthy = (
        previous_state["is_cabinet_worthy"] == 1
        if previous_state is not None
        else False
    )
    previous_cabinet_order = (
        previous_state["cabinet_order"]
        if previous_state is not None
        else None
    )
    cabinet_order = _cabinet_order_for_transition(
        conn,
        previous_is_cabinet_worthy,
        previous_cabinet_order,
        is_cabinet_worthy == 1,
    )
    user_data["cabinet_order"] = cabinet_order

    if watch_state is None and impression is None and is_cabinet_worthy is None:
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
            is_cabinet_worthy,
            cabinet_order
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (media_id) DO UPDATE SET
            watch_state = excluded.watch_state,
            impression = excluded.impression,
            is_cabinet_worthy = excluded.is_cabinet_worthy,
            cabinet_order = excluded.cabinet_order,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            media_id,
            watch_state,
            impression,
            is_cabinet_worthy,
            cabinet_order,
        ),
    )


def _next_cabinet_order(conn):
    row = conn.execute(
        """
        SELECT COALESCE(MAX(cabinet_order), 0) + 1 AS next_order
        FROM media_state
        WHERE is_cabinet_worthy IS 1
        """
    ).fetchone()
    return row["next_order"]


def _cabinet_order_for_transition(
    conn,
    previous_is_cabinet_worthy,
    previous_cabinet_order,
    desired_is_cabinet_worthy,
):
    if not desired_is_cabinet_worthy:
        return None

    if previous_is_cabinet_worthy:
        return previous_cabinet_order

    return _next_cabinet_order(conn)

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
          AND is_cabinet_worthy IS NULL
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
        "media_state": get_media_state(conn, media_id),
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
    if field == "is_cabinet_worthy" and value is not None:
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
            is_cabinet_worthy,
            cabinet_order
        FROM media_state
        WHERE media_id = ?
        """,
        (media_id,),
    ).fetchone()

    return {
        "media_id": media_id,
        "watch_state": state["watch_state"] if state is not None else None,
        "impression": state["impression"] if state is not None else None,
        "is_cabinet_worthy": (
            None
            if state is None or state["is_cabinet_worthy"] is None
            else bool(state["is_cabinet_worthy"])
        ),
        "cabinet_order": (
            state["cabinet_order"] if state is not None else None
        ),
    }

def apply_media_state_patch(
    conn,
    media_id,
    expected_values,
    changes,
):
    """Patch History-editable state fields with optimistic concurrency checks."""
    editable_fields = ("watch_state", "impression", "is_cabinet_worthy")
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

    media_type = _get_media_type(conn, media_id)

    for values in (expected_values, changes):
        if "watch_state" in values:
            validate_watch_state(media_type, values["watch_state"])

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
            "is_cabinet_worthy" in values
            and values["is_cabinet_worthy"] not in {None, True, False}
        ):
            raise ValueError("Unsupported cabinet worthy value.")

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
        for field in editable_fields
    }
    values_to_write.update(normalized_changes)
    cabinet_order = _cabinet_order_for_transition(
        conn,
        current_state["is_cabinet_worthy"] is True,
        current_state["cabinet_order"],
        values_to_write["is_cabinet_worthy"] is True,
    )

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
              AND is_cabinet_worthy IS ?
            """,
            (
                media_id,
                current_state["watch_state"],
                current_state["impression"],
                _to_db_bool(current_state["is_cabinet_worthy"]),
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
                    is_cabinet_worthy,
                    cabinet_order
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    media_id,
                    values_to_write["watch_state"],
                    values_to_write["impression"],
                    _to_db_bool(values_to_write["is_cabinet_worthy"]),
                    cabinet_order,
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

    assignments_to_write = [f"{field} = ?" for field in fields_to_write]
    parameters = [
        _to_db_bool(normalized_changes[field])
        if field == "is_cabinet_worthy"
        else normalized_changes[field]
        for field in fields_to_write
    ]
    if "is_cabinet_worthy" in fields_to_write:
        assignments_to_write.append("cabinet_order = ?")
        parameters.append(cabinet_order)
    assignments = ", ".join(assignments_to_write)
    expected_predicates = " AND ".join(
        f"{field} IS ?"
        for field in fields_to_write
    )
    expected_parameters = [
        _to_db_bool(normalized_expected[field])
        if field == "is_cabinet_worthy"
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
    fields = ("watch_state", "impression", "is_cabinet_worthy")
    state_row = conn.execute(
        """
        SELECT watch_state, impression, is_cabinet_worthy, cabinet_order
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
    cabinet_order = _cabinet_order_for_transition(
        conn,
        database_values["is_cabinet_worthy"] is True,
        state_row["cabinet_order"] if state_row is not None else None,
        values_to_write["is_cabinet_worthy"] is True,
    )

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
                is_cabinet_worthy,
                cabinet_order
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                media_id,
                values_to_write["watch_state"],
                values_to_write["impression"],
                _to_db_bool(values_to_write["is_cabinet_worthy"]),
                cabinet_order,
            ),
        )
        return len(changed_fields)

    assignments_to_write = [f"{field} = ?" for field in changed_fields]
    parameters = [
        _to_db_bool(values_to_write[field])
        if field == "is_cabinet_worthy"
        else values_to_write[field]
        for field in changed_fields
    ]
    if "is_cabinet_worthy" in changed_fields:
        assignments_to_write.append("cabinet_order = ?")
        parameters.append(cabinet_order)
    assignments = ", ".join(assignments_to_write)
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

def _to_db_bool(value):
    if value is None:
        return None

    return 1 if value else 0
