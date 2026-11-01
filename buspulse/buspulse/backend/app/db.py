import pathlib
import sqlite3

from . import config

SCHEMA_FILE = pathlib.Path(__file__).resolve().parent.parent / "schema.sql"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def get_db():
    """FastAPI dependency."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()
