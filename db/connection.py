from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

DB_PATH = DATA_DIR / "media.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
SEED_PATH = BASE_DIR / "db" / "seed.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        drop_database_views(conn)
        migrate_database(conn)
        apply_database_schema(conn)
        seed_database(conn)
        conn.commit()


def apply_database_schema(conn: sqlite3.Connection) -> None:
    run_sql_script(conn, SCHEMA_PATH)


def seed_database(conn: sqlite3.Connection) -> None:
    run_sql_script(conn, SEED_PATH)


def run_sql_script(conn: sqlite3.Connection, script_path: Path) -> None:
    conn.executescript(script_path.read_text(encoding="utf-8"))


def drop_database_views(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS series_episode_watch_history;")
    conn.execute("DROP VIEW IF EXISTS series_summary;")


def migrate_database(conn: sqlite3.Connection) -> None:
    _migrate_media_imdb_id_nullable(conn)
    _migrate_media_tmdb_freshness_columns(conn)
    _migrate_media_watch_providers_checked_at_removed(conn)


def _migrate_media_tmdb_freshness_columns(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(media)")
    media_columns = {row["name"] for row in cursor.fetchall()}

    if not media_columns:
        return

    freshness_columns = (
        "last_tmdb_metadata_checked_at",
        "last_tmdb_posters_checked_at",
        "last_tmdb_watch_providers_checked_at",
    )

    for column_name in freshness_columns:
        if column_name not in media_columns:
            conn.execute(f"ALTER TABLE media ADD COLUMN {column_name} TEXT;")


def _migrate_media_watch_providers_checked_at_removed(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(media_watch_providers)")
    media_watch_provider_columns = {row["name"] for row in cursor.fetchall()}

    if "checked_at" not in media_watch_provider_columns:
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF;")

    try:
        conn.executescript(
            """
            DROP INDEX IF EXISTS idx_media_watch_providers_media_id;

            CREATE TABLE media_watch_providers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                media_id INTEGER NOT NULL,
                provider_tmdb_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                country_code TEXT NOT NULL,
                access_type TEXT NOT NULL,

                FOREIGN KEY (media_id)
                    REFERENCES media(id)
                    ON DELETE CASCADE,

                UNIQUE (
                    media_id,
                    provider_tmdb_id,
                    country_code,
                    access_type
                ),

                CHECK (country_code GLOB '[A-Z][A-Z]'),
                CHECK (access_type IN ('flatrate', 'rent', 'buy'))
            );

            INSERT INTO media_watch_providers_new (
                id,
                media_id,
                provider_tmdb_id,
                provider_name,
                country_code,
                access_type
            )
            SELECT
                id,
                media_id,
                provider_tmdb_id,
                provider_name,
                country_code,
                access_type
            FROM media_watch_providers;

            DROP TABLE media_watch_providers;
            ALTER TABLE media_watch_providers_new RENAME TO media_watch_providers;

            CREATE INDEX idx_media_watch_providers_media_id
                ON media_watch_providers (media_id);
            """
        )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")


def _migrate_media_imdb_id_nullable(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(media)")
    media_columns = {row["name"]: row for row in cursor.fetchall()}
    imdb_id_column = media_columns.get("imdb_id")

    if imdb_id_column is None or not imdb_id_column["notnull"]:
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF;")

    try:
        conn.executescript(
            """
            DROP VIEW IF EXISTS series_episode_watch_history;
            DROP VIEW IF EXISTS series_summary;

            CREATE TABLE media_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                tmdb_id INTEGER NOT NULL,
                imdb_id TEXT,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                original_title TEXT,
                production_status TEXT,
                release_date TEXT,
                runtime_min INTEGER,

                UNIQUE (tmdb_id, media_type),
                UNIQUE (imdb_id),

                CHECK (media_type IN ('movie', 'series', 'episode')),
                CHECK (
                    release_date IS NULL
                    OR (
                        release_date = date(release_date)
                        AND release_date GLOB '????-??-??'
                    )
                ),
                CHECK (runtime_min IS NULL OR runtime_min >= 0)
            );

            INSERT INTO media_new (
                id,
                tmdb_id,
                imdb_id,
                media_type,
                title,
                original_title,
                production_status,
                release_date,
                runtime_min
            )
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
            FROM media;

            DROP TABLE media;
            ALTER TABLE media_new RENAME TO media;
            """
        )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")
