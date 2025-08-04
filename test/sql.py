from datetime import datetime, timedelta
import sqlite3

conn = sqlite3.connect("database/main.db")
cur = conn.cursor()

# now = datetime.now()

# updates = {
#     'oER2-7u6e': now + timedelta(days=1),
#     'oER2-7u6B': now + timedelta(days=1.5),
#     'oER2-7u6L': now + timedelta(days=3),
#     'oER2-7u6x': now + timedelta(days=3.5),
#     }

# for assignment_id, due_date in updates.items():
#     iso_date = due_date.isoformat()
#     cur.execute("UPDATE user_assignments SET status = 'OPEN' WHERE assignment_id = ?", (assignment_id,))
#     cur.execute("UPDATE assignment SET due_date = ? WHERE assignment_id = ?", (iso_date, assignment_id))


command = """CREATE TABLE log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    level TEXT,          -- INFO, WARNING, ERROR, DEBUG
    source TEXT,         -- e.g., "scheduler", "notifier", "scraper", "webhook"
    message TEXT,
    data TEXT            -- optional JSON blob (assignment_id, user_id etc.)
);

"""
cur.executescript(command)
# Create Course table
cur.execute("""
CREATE TABLE IF NOT EXISTS course (
    course_id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    courseNumber TEXT,
    thumbnail TEXT,
    semester TEXT
)
""")

# Create Assignment table
cur.execute("""
CREATE TABLE IF NOT EXISTS assignment (
    assignment_id TEXT PRIMARY KEY,
    course_id TEXT,
    due_date DATETIME,
    name TEXT,
    type TEXT,
    FOREIGN KEY (course_id) REFERENCES course(course_id)
)
""")

# Create User table
cur.execute("""
CREATE TABLE IF NOT EXISTS user (
    user_id TEXT PRIMARY KEY,
    cname TEXT,
    cpass TEXT,
    Line_uid TEXT
)
""")

# Create User_Assignment table
cur.execute("""
CREATE TABLE IF NOT EXISTS user_assignments (
    user_id TEXT,
    assignment_id TEXT,
    1d_notified BOOLEAN DEFAULT FALSE,
    3d_notified BOOLEAN DEFAULT FALSE,
    status TEXT,
    PRIMARY KEY (user_id, assignment_id),
    FOREIGN KEY (user_id) REFERENCES user(user_id),
    FOREIGN KEY (assignment_id) REFERENCES assignment(assignment_id)
)
""")



conn.commit()
conn.close()



