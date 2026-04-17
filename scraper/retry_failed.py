# retry_failed.py
import sqlite3

conn = sqlite3.connect("state.db")

result = conn.execute("""
    UPDATE scrape_queue
    SET status   = 'pending',
        attempts = 0,
        last_error = NULL
    WHERE status = 'failed'
""")

print(f"Reset {result.rowcount} trains back to pending")
conn.commit()
conn.close()