import psycopg2
import psycopg2.extras
from contextlib import contextmanager

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "train_db",
    "user":     "postgres",
    "password": "20357",   # ← change this
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