"""Persistence for the ordered Cabinet collection."""

from app.media_draft.builder import build_media_draft_from_db
from app.media_repository.errors import ConcurrentEditError


def initialize_cabinet_order(conn):
    """Append unordered worthy media after any existing custom order."""
    existing = conn.execute(
        """
        SELECT MIN(cabinet_order) AS minimum_order
        FROM media_state
        WHERE is_cabinet_worthy IS 1
          AND cabinet_order IS NOT NULL
        """
    ).fetchone()
    unordered = conn.execute(
        """
        SELECT media_id
        FROM media_state
        WHERE is_cabinet_worthy IS 1
          AND cabinet_order IS NULL
        ORDER BY created_at DESC, media_id DESC
        """
    ).fetchall()

    if not unordered:
        return 0

    minimum_order = existing["minimum_order"]
    next_order = (
        minimum_order - 1
        if minimum_order is not None
        else len(unordered)
    )

    for offset, row in enumerate(unordered):
        conn.execute(
            """
            UPDATE media_state
            SET cabinet_order = ?, updated_at = CURRENT_TIMESTAMP
            WHERE media_id = ?
              AND is_cabinet_worthy IS 1
              AND cabinet_order IS NULL
            """,
            (next_order - offset, row["media_id"]),
        )

    return len(unordered)


def load_cabinet_drafts(conn):
    rows = conn.execute(
        """
        SELECT media.*
        FROM media
        JOIN media_state
          ON media_state.media_id = media.id
        WHERE media_state.is_cabinet_worthy IS 1
        ORDER BY media_state.cabinet_order DESC
        """
    ).fetchall()
    return [build_media_draft_from_db(conn, row) for row in rows]


def initialize_and_load_cabinet(conn):
    """Initialize missing order values and load the Cabinet atomically."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        initialize_cabinet_order(conn)
        drafts = load_cabinet_drafts(conn)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return drafts


def persist_cabinet_reorder(conn, expected_media_ids, desired_media_ids):
    """Validate and persist one complete Cabinet reorder atomically."""
    expected_media_ids = list(expected_media_ids)
    desired_media_ids = list(desired_media_ids)

    if (
        len(desired_media_ids) != len(set(desired_media_ids))
        or set(desired_media_ids) != set(expected_media_ids)
        or len(expected_media_ids) != len(set(expected_media_ids))
    ):
        raise ValueError("Cabinet reorder must contain each expected media once.")

    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            """
            SELECT media_id, cabinet_order
            FROM media_state
            WHERE is_cabinet_worthy IS 1
            ORDER BY cabinet_order DESC
            """
        ).fetchall()
        current_media_ids = [row["media_id"] for row in rows]

        if current_media_ids != expected_media_ids:
            raise ConcurrentEditError(
                "Cabinet membership or order changed before the reorder."
            )

        current_orders = {
            row["media_id"]: row["cabinet_order"]
            for row in rows
        }
        normalized_orders = {
            media_id: len(desired_media_ids) - index
            for index, media_id in enumerate(desired_media_ids)
        }
        updated_count = 0

        for media_id in desired_media_ids:
            cabinet_order = normalized_orders[media_id]
            if current_orders[media_id] == cabinet_order:
                continue

            cursor = conn.execute(
                """
                UPDATE media_state
                SET cabinet_order = ?, updated_at = CURRENT_TIMESTAMP
                WHERE media_id = ?
                  AND is_cabinet_worthy IS 1
                  AND cabinet_order IS ?
                """,
                (cabinet_order, media_id, current_orders[media_id]),
            )
            if cursor.rowcount != 1:
                raise ConcurrentEditError(
                    "Cabinet order changed while the reorder was saved."
                )
            updated_count += 1
    except Exception:
        conn.rollback()
        raise

    conn.commit()
    return {
        "media_ids": desired_media_ids,
        "orders": normalized_orders,
        "updated_count": updated_count,
    }
