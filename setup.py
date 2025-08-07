import sqlite3

conn = sqlite3.connect("database/main.db")
cur = conn.cursor()

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
    notify_1d BOOLEAN DEFAULT FALSE,
    notify_3d BOOLEAN DEFAULT FALSE,
    status TEXT,
    PRIMARY KEY (user_id, assignment_id),
    FOREIGN KEY (user_id) REFERENCES user(user_id),
    FOREIGN KEY (assignment_id) REFERENCES assignment(assignment_id)
)
""")



conn.commit()
conn.close()

conn = sqlite3.connect("database/log.db")
cur = conn.cursor()
cur.execute("""CREATE TABLE log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now', '+7 hours')),
    level TEXT,          -- INFO, WARNING, ERROR, DEBUG
    source TEXT,        
    message TEXT,
    data TEXT            -- optional JSON blob (assignment_id, user_id etc.)
);"""
)
conn.commit()
conn.close()



