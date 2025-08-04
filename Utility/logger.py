import sqlite3

DB_PATH = "database/log.db"

def log(level, source, message, data=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO log (level, source, message, data)
        VALUES (?, ?, ?, ?)
    """, (level, source, message, data if data else None))

    conn.commit()
    conn.close()

# Convenience shortcuts
def info(source, message, data=None): log("INFO", source, message, data)
def warn(source, message, data=None): log("WARNING", source, message, data)
def error(source, message, data=None): log("ERROR", source, message, data)
def debug(source, message, data=None): log("DEBUG", source, message, data)
