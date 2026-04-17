# categorize_failures.py
import sqlite3

conn = sqlite3.connect("state.db")

rows = conn.execute("""
    SELECT train_no, last_error
    FROM scrape_queue
    WHERE status = 'failed'
    ORDER BY last_error, train_no
""").fetchall()

blocked     = [t for t, e in rows if e == "blocked_or_redirected"]
parse_error = [t for t, e in rows if e == "parse_error"]

print(f"Total failed     : {len(rows)}")
print(f"blocked          : {len(blocked)}")
print(f"parse_error      : {len(parse_error)}")
print()
print("Blocked trains:")
print(blocked)
print()
print("Parse error trains:")
print(parse_error)

conn.close()