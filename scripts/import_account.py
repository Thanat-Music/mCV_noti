"""Explicit one-account migration; no output of credentials, no overwrites."""
import argparse
import os
from pathlib import Path
import sqlite3


def import_account(source, destination, user="u1"):
    src = sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = src.execute("SELECT user_id,cname,cpass,Line_uid FROM user WHERE user_id=?", (user,)).fetchone()
    finally:
        src.close()
    if not row:
        raise RuntimeError("selected_account_missing")
    dst = sqlite3.connect(destination)
    try:
        with dst:
            dst.execute("CREATE TABLE IF NOT EXISTS user(user_id TEXT PRIMARY KEY,cname TEXT,cpass TEXT,Line_uid TEXT)")
            existing = dst.execute("SELECT user_id,cname,cpass,Line_uid FROM user WHERE user_id=?", (user,)).fetchone()
            if existing and existing != row:
                raise RuntimeError("existing_account_differs_no_overwrite")
            dst.execute("INSERT OR IGNORE INTO user(user_id,cname,cpass,Line_uid) VALUES(?,?,?,?)", row)
    finally:
        dst.close()


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--user", default="u1")
    args = parser.parse_args()
    import_account(args.source, args.destination, args.user)
    print("Selected account imported; existing receiver and application state preserved.")
