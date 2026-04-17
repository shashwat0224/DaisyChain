# retry_parse_errors.py
import sqlite3

conn = sqlite3.connect("state.db")
result = conn.execute("""
    UPDATE scrape_queue
    SET status     = 'pending',
        attempts   = 0,
        last_error = NULL
    WHERE status     = 'failed'
    AND   last_error = 'parse_error'
""")
print(f"Reset {result.rowcount} parse error trains")
conn.commit()
conn.close()