import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "state.db"


def init_queue(train_numbers: list, db_path: str = DB_PATH):
    """
    Creates SQLite queue and populates with train numbers.
    Safe to re-run — completed trains are never reset.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrape_queue (
            train_no   TEXT PRIMARY KEY,
            status     TEXT DEFAULT 'pending',
            worker_id  INTEGER,
            attempts   INTEGER DEFAULT 0,
            last_error TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.executemany(
        "INSERT OR IGNORE INTO scrape_queue (train_no) VALUES (?)",
        [(str(t),) for t in train_numbers]
    )
    conn.commit()
    conn.close()
    logger.info(f"Queue ready: {len(train_numbers)} trains loaded")


def claim_next(worker_id: int, db_path: str = DB_PATH) -> Optional[str]:
    """
    Atomically claims the next pending train for this worker.
    Also auto-reclaims trains stuck in_progress for over 10 min (crashed workers).
    """
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("""
            UPDATE scrape_queue
            SET status = 'pending', worker_id = NULL
            WHERE status = 'in_progress'
            AND updated_at < datetime('now', '-10 minutes')
        """)

        row = conn.execute("""
            SELECT train_no FROM scrape_queue
            WHERE status = 'pending'
            AND attempts < 3
            ORDER BY train_no
            LIMIT 1
        """).fetchone()

        if not row:
            return None

        train_no = row[0]
        conn.execute("""
            UPDATE scrape_queue
            SET status     = 'in_progress',
                worker_id  = ?,
                attempts   = attempts + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE train_no = ?
        """, (worker_id, train_no))
        conn.commit()
        return train_no
    finally:
        conn.close()


def mark_done(train_no: str, db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("""
        UPDATE scrape_queue
        SET status = 'done', updated_at = CURRENT_TIMESTAMP
        WHERE train_no = ?
    """, (train_no,))
    conn.commit()
    conn.close()


def mark_failed(train_no: str, error: str, db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("""
        UPDATE scrape_queue
        SET status     = 'failed',
            last_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE train_no = ?
    """, (error[:500], train_no))
    conn.commit()
    conn.close()


def reset_to_pending(train_no: str, db_path: str = DB_PATH):
    """
    Used when mobile layout is detected.
    Returns train to queue without counting it as a failure attempt.
    """
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("""
        UPDATE scrape_queue
        SET status     = 'pending',
            worker_id  = NULL,
            attempts   = MAX(0, attempts - 1),
            updated_at = CURRENT_TIMESTAMP
        WHERE train_no = ?
    """, (train_no,))
    conn.commit()
    conn.close()


def get_progress(db_path: str = DB_PATH) -> dict:
    conn = sqlite3.connect(db_path, timeout=10)
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM scrape_queue GROUP BY status"
    ).fetchall()
    conn.close()
    return dict(rows)


def get_failed_trains(db_path: str = DB_PATH) -> list:
    conn = sqlite3.connect(db_path, timeout=10)
    rows = conn.execute("""
        SELECT train_no, last_error FROM scrape_queue
        WHERE status = 'failed'
        ORDER BY train_no
    """).fetchall()
    conn.close()
    return rows


def get_true_total(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path, timeout=10)
    total = conn.execute("SELECT COUNT(*) FROM scrape_queue").fetchone()[0]
    conn.close()
    return total