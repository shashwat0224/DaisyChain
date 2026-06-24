import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv
from pathlib import Path

# Load .env from backend/ folder
load_dotenv(Path(__file__).resolve().parent.parent / 'backend' / '.env')

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME",     "train_db"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

@contextmanager
def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_session(readonly=True)   # search never writes
    try:
        yield conn
    finally:
        conn.close()


def execute(query: str, params: tuple = ()) -> list[dict]:
    """
    Run a SELECT and return list of dicts.
    Used by both direct and indirect search.
    """
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]