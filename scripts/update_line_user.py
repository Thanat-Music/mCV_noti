"""Update u1's LINE recipient ID without changing CourseVille credentials."""
import argparse
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path


def update(database, line_id):
    line_id = line_id.strip()
    if not re.fullmatch(r"U[0-9a-fA-F]{32}", line_id):
        raise ValueError("LINE user ID must be U followed by 32 hexadecimal characters.")
    line_id = "U" + line_id[1:].lower()
    # Read/write mode refuses to create a database at an incorrect path.
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=rw", uri=True)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM user WHERE user_id='u1'").fetchone() is None:
            raise ValueError("Account u1 does not exist in this database.")
        duplicate = db.execute(
            "SELECT 1 FROM user WHERE lower(Line_uid)=lower(?) AND user_id!='u1'",
            (line_id,),
        ).fetchone()
        if duplicate:
            raise ValueError("This LINE user ID is already assigned to another account.")
        db.execute("UPDATE user SET Line_uid=? WHERE user_id='u1'", (line_id,))
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "admin_users" in tables:
            db.execute("UPDATE admin_users SET revision=revision+1 WHERE user_id='u1'")
        if "admin_audit" in tables:
            db.execute("INSERT INTO admin_audit(at,action,user_id) VALUES(?,?,?)",
                       (time.time(), "user.updated", "u1"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path,
                        default=Path(__file__).resolve().parents[1] / "database" / "main.db")
    args = parser.parse_args()
    try:
        line_id = input("New LINE Messaging API user ID for u1: ")
        update(args.database, line_id)
    except (ValueError, sqlite3.Error, EOFError) as exc:
        parser.exit(1, f"Update failed: {exc}\n")
    print("Updated u1's LINE recipient ID. CourseVille credentials are unchanged.")


if __name__ == "__main__":
    main()
