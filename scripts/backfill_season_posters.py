import argparse
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app.draft_saver as draft_saver
import app.media_repository as media_repository
import app.tmdb_fetcher as tmdb_fetcher
from db.connection import get_connection


def backfill_season_posters(
    conn,
    *,
    apply=False,
    poster_dir=draft_saver.DEFAULT_POSTER_DIR,
    poster_size=draft_saver.TMDB_POSTER_SIZE,
):
    """Report or fill missing canonical TMDB season posters for every series."""
    results = []

    for series in _get_series_rows(conn):
        result = {
            "series_id": series["id"],
            "tmdb_id": series["tmdb_id"],
            "title": series["title"],
            "missing_count": 0,
            "inserted_count": 0,
            "poster_downloads": _empty_poster_downloads(),
            "status": "ok",
        }

        try:
            canonical_posters = (
                tmdb_fetcher.get_tmdb_series_primary_season_posters(
                    series["tmdb_id"]
                )
            )
            missing_posters = _get_missing_season_posters(
                conn,
                series["id"],
                canonical_posters,
            )
            result["missing_count"] = len(missing_posters)

            if apply:
                downloads = draft_saver.download_missing_draft_posters(
                    {"posters": missing_posters},
                    poster_dir=poster_dir,
                    poster_size=poster_size,
                    fail_on_error=False,
                )
                result["poster_downloads"] = downloads
                persistable_posters = _without_failed_tmdb_posters(
                    missing_posters,
                    downloads,
                )
                before_count = _count_series_season_posters(
                    conn,
                    series["id"],
                )

                with conn:
                    media_repository.insert_missing_series_season_posters(
                        conn,
                        series["id"],
                        persistable_posters,
                    )

                    if not downloads.get("failed"):
                        media_repository.update_media_tmdb_posters_checked_at(
                            conn,
                            series["id"],
                            tmdb_fetcher.current_sqlite_timestamp(),
                        )

                after_count = _count_series_season_posters(
                    conn,
                    series["id"],
                )
                result["inserted_count"] = after_count - before_count

                if downloads.get("failed"):
                    result["status"] = "failed"
                    result["error"] = _format_download_failures(downloads)
        except Exception as exc:
            conn.rollback()
            result["status"] = "failed"
            result["error"] = str(exc)

        results.append(result)

    return results


def _get_series_rows(conn):
    return conn.execute(
        """
        SELECT id, tmdb_id, title
        FROM media
        WHERE media_type = 'series'
        ORDER BY title COLLATE NOCASE, id
        """
    ).fetchall()


def _get_missing_season_posters(conn, series_id, canonical_posters):
    existing_seasons = {
        row["season_num"]
        for row in conn.execute(
            """
            SELECT DISTINCT season_num
            FROM season_posters
            WHERE series_id = ?
            """,
            (series_id,),
        ).fetchall()
    }
    missing = []
    seen_seasons = set()

    for poster in canonical_posters:
        season_num = poster.get("season_num")

        if season_num in existing_seasons or season_num in seen_seasons:
            continue

        seen_seasons.add(season_num)
        missing.append(poster)

    return missing


def _without_failed_tmdb_posters(posters, downloads):
    failed_filenames = {
        str(failure.get("filename"))
        for failure in downloads.get("failed", [])
        if failure.get("filename") is not None
    }

    return [
        poster
        for poster in posters
        if poster.get("source", "tmdb") != "tmdb"
        or str(poster.get("filename")) not in failed_filenames
    ]


def _count_series_season_posters(conn, series_id):
    return conn.execute(
        "SELECT COUNT(*) FROM season_posters WHERE series_id = ?",
        (series_id,),
    ).fetchone()[0]


def _empty_poster_downloads():
    return {"downloaded": [], "skipped": [], "failed": []}


def _format_download_failures(downloads):
    filenames = [
        str(failure.get("filename"))
        for failure in downloads.get("failed", [])
    ]
    return "poster download failed: " + ", ".join(filenames)


def print_results(results, *, apply):
    mode = "apply" if apply else "dry-run"

    for result in results:
        line = (
            f"[{mode}] {result['title']} (tmdb={result['tmdb_id']}): "
            f"missing={result['missing_count']}"
        )

        if apply:
            line += f" inserted={result['inserted_count']}"

        if result["status"] == "failed":
            line += f" error={result.get('error', 'unknown error')}"

        print(line)

    failed_count = sum(
        1 for result in results if result["status"] == "failed"
    )
    print(f"series={len(results)} failures={failed_count}")


def _build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Fill missing canonical TMDB season posters.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="List missing season posters without writing files or database rows.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Download and insert missing season posters.",
    )
    return parser


def main(argv=None):
    args = _build_argument_parser().parse_args(argv)

    with get_connection() as conn:
        results = backfill_season_posters(conn, apply=args.apply)

    print_results(results, apply=args.apply)
    return 1 if any(result["status"] == "failed" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
