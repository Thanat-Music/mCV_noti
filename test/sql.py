from datetime import datetime, timedelta
import sqlite3

conn = sqlite3.connect("database/main.db")
cur = conn.cursor()

now = datetime.now()

updates = {
    'oER2-7u6e': now + timedelta(days=1),
    'oER2-7u6B': now + timedelta(days=1.5),
    'oER2-7u6L': now + timedelta(days=3),
    'oER2-7u6x': now + timedelta(days=3.5),
    }

for assignment_id, due_date in updates.items():
    iso_date = due_date.isoformat()
    cur.execute("UPDATE user_assignments SET status = 'OPEN' WHERE assignment_id = ?", (assignment_id,))
    cur.execute("UPDATE assignment SET due_date = ? WHERE assignment_id = ?", (iso_date, assignment_id))


# command = """CREATE TABLE log (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
#     level TEXT,          -- INFO, WARNING, ERROR, DEBUG
#     source TEXT,         -- e.g., "scheduler", "notifier", "scraper", "webhook"
#     message TEXT,
#     data TEXT            -- optional JSON blob (assignment_id, user_id etc.)
# );

# """
# cur.executescript(command)


conn.commit()
conn.close()



