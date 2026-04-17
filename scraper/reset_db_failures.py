# Run this once as a script: reset_db_failures.py

import sqlite3

conn = sqlite3.connect("state.db")

# Reset only trains that failed due to the null constraint — not genuine parse errors
result = conn.execute("""
    UPDATE scrape_queue
    SET status   = 'pending',
        attempts = 0,
        last_error = NULL
    WHERE status = 'failed'
    AND last_error LIKE '%null value in column%'
""")

print(f"Reset {result.rowcount} trains back to pending")
conn.commit()
conn.close()