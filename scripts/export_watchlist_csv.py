import csv
from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.connection import DATA_DIR, DB_PATH


FIELDNAMES = (
    "imdb_id",
    "tmdb_id",
    "media_type",
    "title",
    "watch_state",
    "impression",
    "is_collection_pick",
    "notes",
    "watch_history",
    "lists",
)


def collect_watchlist_rows(conn):
    """Return CSV-ready rows for every media item present in media_state."""
    notes_by_media_id = _get_notes_by_media_id(conn)
    history_by_media_id = _get_watch_history_by_media_id(conn)
    lists_by_media_id = _get_lists_by_media_id(conn)
    export_rows = []

    for media in _get_watchlist_media(conn):
        media_id = media["media_id"]
        row = {
            "imdb_id": media["imdb_id"] or "",
            "tmdb_id": media["tmdb_id"],
            "media_type": media["media_type"],
            "title": _format_title(media),
            "watch_state": media["watch_state"] or "",
            "impression": media["impression"] or "",
            "is_collection_pick": _format_optional_bool(
                media["is_collection_pick"]
            ),
            "notes": _to_json(notes_by_media_id[media_id]),
            "watch_history": _to_json(history_by_media_id[media_id]),
            "lists": _to_json(lists_by_media_id[media_id]),
        }
        export_rows.append((media_id, row))

    export_rows.sort(
        key=lambda item: (
            item[1]["title"].casefold(),
            item[0],
        )
    )
    return [row for _media_id, row in export_rows]


def write_csv_atomic(rows, output_path):
    """Write rows to output_path without leaving a partial destination file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.DictWriter(
                temporary_file,
                fieldnames=FIELDNAMES,
                extrasaction="raise",
            )
            writer.writeheader()
            writer.writerows(rows)

        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def default_export_path(today=None, data_dir=None):
    export_date = today or date.today()
    export_data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    return export_data_dir / f"media_export_{export_date.isoformat()}.csv"


def get_read_only_connection(db_path):
    database_uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(database_uri, uri=True)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _get_watchlist_media(conn):
    return conn.execute(
        """
        SELECT
            m.id AS media_id,
            m.imdb_id,
            m.tmdb_id,
            m.media_type,
            m.title,
            ms.watch_state,
            ms.impression,
            ms.is_collection_pick,
            parent_series.title AS series_title,
            ed.season_num,
            ed.episode_num
        FROM media m
        JOIN media_state ms
            ON ms.media_id = m.id
        LEFT JOIN episode_details ed
            ON ed.media_id = m.id
        LEFT JOIN media parent_series
            ON parent_series.id = ed.series_id
           AND parent_series.media_type = 'series'
        """
    ).fetchall()


def _get_notes_by_media_id(conn):
    notes_by_media_id = defaultdict(list)
    rows = conn.execute(
        """
        SELECT mn.media_id, mn.note
        FROM media_notes mn
        JOIN media_state ms
            ON ms.media_id = mn.media_id
        ORDER BY mn.media_id, mn.created_at, mn.id
        """
    ).fetchall()

    for row in rows:
        notes_by_media_id[row["media_id"]].append(row["note"])

    return notes_by_media_id


def _get_watch_history_by_media_id(conn):
    history_by_media_id = defaultdict(list)
    rows = conn.execute(
        """
        SELECT
            wh.media_id,
            wh.date_earliest,
            wh.date_latest
        FROM watch_history wh
        JOIN media_state ms
            ON ms.media_id = wh.media_id
        ORDER BY wh.media_id, wh.created_at, wh.id
        """
    ).fetchall()

    for row in rows:
        earliest = row["date_earliest"] or ""
        latest = row["date_latest"] or ""
        history_by_media_id[row["media_id"]].append(
            f"{earliest}:{latest}"
        )

    return history_by_media_id


def _get_lists_by_media_id(conn):
    lists_by_media_id = defaultdict(list)
    rows = conn.execute(
        """
        SELECT ml.media_id, l.name
        FROM media_lists ml
        JOIN media_state ms
            ON ms.media_id = ml.media_id
        JOIN lists l
            ON l.id = ml.list_id
        ORDER BY
            ml.media_id,
            l.name COLLATE NOCASE,
            l.name,
            l.id
        """
    ).fetchall()

    for row in rows:
        lists_by_media_id[row["media_id"]].append(row["name"])

    return lists_by_media_id


def _format_title(media):
    if media["media_type"] != "episode":
        return media["title"]

    if (
        media["series_title"] is None
        or media["season_num"] is None
        or media["episode_num"] is None
    ):
        raise ValueError(
            f"episode media_id={media['media_id']} has incomplete series details"
        )

    return (
        f"{media['series_title']}: {media['title']} "
        f"S{media['season_num']}:E{media['episode_num']}"
    )


def _format_optional_bool(value):
    if value is None:
        return ""

    return "true" if bool(value) else "false"


def _to_json(values):
    return json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def main():
    if not DB_PATH.is_file():
        print(f"error: database not found: {DB_PATH}", file=sys.stderr)
        return 1

    output_path = default_export_path()

    try:
        with get_read_only_connection(DB_PATH) as conn:
            rows = collect_watchlist_rows(conn)

        write_csv_atomic(rows, output_path)
    except Exception as exc:
        print(f"error: export failed: {exc}", file=sys.stderr)
        return 1

    print(f"exported {len(rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
