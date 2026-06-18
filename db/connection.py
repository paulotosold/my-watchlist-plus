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
        with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())

        with open(SEED_PATH, "r", encoding="utf-8") as seed_file:
            conn.executescript(seed_file.read())

        conn.commit()