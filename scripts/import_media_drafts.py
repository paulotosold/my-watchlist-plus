from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.media_draft import build_and_save_media_drafts_from_imdb_ids
from db.connection import get_connection, initialize_database


#IMDB_IDS = ["tt2920540", "tt0094625", "tt4538072", "tt5710976", "tt13309742", "tt2380307", "tt0074330", "tt1160419", "tt15239678", "tt0113568", "tt9218128", "tt1798709", "tt5104604", "tt0209144", "tt5109784", "tt1954701", "tt0907657", "tt11737520", "tt0851578", "tt6751668", "tt16418808", "tt5950044", "tt32150119", "tt0209463", "tt11674072", "tt0243017", "tt0406375"]
IMDB_IDS = ["tt2920540", "tt4538072", "tt9053874", "tt13309742", "tt32150119", "tt0094582"]
#IMDB_IDS = ["tt0243017", "tt0209144", "tt5109784", "tt1954701", "tt0907657", "tt11737520", "tt0851578", "tt6751668",]

def main():
    if not IMDB_IDS:
        print("No IMDb IDs configured. Add IDs to IMDB_IDS in this script.")
        return

    initialize_database()

    conn = get_connection()

    try:
        results = build_and_save_media_drafts_from_imdb_ids(conn, IMDB_IDS)
    finally:
        conn.close()

    print_results(results)


def print_results(results):
    saved_count = sum(1 for result in results if result["status"] == "saved")
    error_count = sum(1 for result in results if result["status"] == "error")

    print(f"saved: {saved_count}")
    print(f"errors: {error_count}")

    for result in results:
        if result["status"] == "saved":
            downloads = result["poster_downloads"]
            print(
                "[saved] "
                f"{result['imdb_id']} -> media_id={result['media_id']} "
                f"{result['media_type']} {result['title']!r} "
                f"posters downloaded={len(downloads['downloaded'])} "
                f"skipped={len(downloads['skipped'])} "
                f"failed={len(downloads['failed'])}"
            )

            for failure in downloads["failed"]:
                print(
                    "  poster failed: "
                    f"{failure['filename']}: {failure['error']}"
                )

        else:
            print(f"[error] {result['imdb_id']}: {result['error']}")


if __name__ == "__main__":
    main()
