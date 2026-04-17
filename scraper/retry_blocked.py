# retry_blocked.py
import sqlite3

conn = sqlite3.connect("state.db")
result = conn.execute("""
    UPDATE scrape_queue
    SET status     = 'pending',
        attempts   = 0,
        last_error = NULL
    WHERE status     = 'failed'
    AND   last_error = 'blocked_or_redirected'
""")
print(f"Reset {result.rowcount} blocked trains")
conn.commit()
conn.close()