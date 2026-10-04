"""Receiver identity and durable inbox in one SQLite transaction domain."""
import json
import os
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.path, timeout=10)
        os.chmod(self.path, 0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS push_state (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS push_inbox (
                channel TEXT NOT NULL, version TEXT NOT NULL, received REAL NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY(channel, version));
            CREATE TABLE IF NOT EXISTS push_refresh (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                requested INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0);
            INSERT OR IGNORE INTO push_refresh(singleton) VALUES(1);
        ''')

    def get(self, name, default=None):
        row = self.db.execute("SELECT value FROM push_state WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, name, value):
        with self.db:
            self.db.execute("INSERT INTO push_state VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                            (name, json.dumps(value)))

    def accept(self, channel, version, payload, state="pending"):
        """Commit event and refresh generation together BEFORE network ack."""
        with self.db:
            inserted = self.db.execute(
                "INSERT OR IGNORE INTO push_inbox(channel,version,received,payload,state) VALUES(?,?,?,?,?)",
                (channel, str(version), time.time(), json.dumps(payload), state)).rowcount
            if inserted:
                # Even malformed/empty payloads can signal a required reconciliation.
                self.db.execute("UPDATE push_refresh SET requested=requested+1 WHERE singleton=1")
        return bool(inserted)

    def counts(self):
        return dict(self.db.execute("SELECT state,COUNT(*) FROM push_inbox GROUP BY state"))

    @staticmethod
    def status(path):
        path = Path(path).resolve()
        if not path.exists():
            return {"registered": False, "inbox": {}, "state_exists": False}
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
        try:
            values = {name: json.loads(value) for name, value in db.execute("SELECT name,value FROM push_state")}
            identity = values.get("identity", {})
            return {"registered": bool(identity.get("endpoint")),
                "published_current_endpoint": bool(identity.get("endpoint")) and
                    values.get("published_endpoint") == identity.get("endpoint"),
                "verified_at": values.get("verified_at"),
                "inbox": dict(db.execute("SELECT state,COUNT(*) FROM push_inbox GROUP BY state")),
                "last_received_at": db.execute("SELECT MAX(received) FROM push_inbox").fetchone()[0],
                "last_connection_at": values.get("connected_at"),
                "note": "Timestamps and registration do not prove current connectivity or CourseVille delivery."}
        finally:
            db.close()

    def close(self):
        self.db.close()


class ReceiverLock:
    """Prevent two processes from using the same receiver identity."""
    def __init__(self, path):
        self.path = Path(str(path) + ".lock")

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, "a+b")
        self.file.seek(0)
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("receiver_already_running") from None
        return self

    def __exit__(self, *args):
        self.file.close()
