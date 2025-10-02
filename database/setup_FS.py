import sqlite3
from google.cloud import firestore

# --- Step 1: Export SQLite ---
def export_sqlite(db_path="main.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    data = {}
    cursor.execute(f"SELECT * FROM user")
    rows = cursor.fetchall()
    data["user"] = [dict(row) for row in rows]

    conn.close()
    return data


# --- Step 2: Firestore Migration ---
def migrate_to_firestore(data):
    db = firestore.Client()

    # --- Users collection ---
    for user in data["user"]:
        Line_uid = user["Line_uid"]
        user_doc = {
            "cname": user.get("cname"),
            "cpass": user.get("cpass"),
            "user_id": user.get("user_id"),
        }
        db.collection("Users").document(Line_uid).set(user_doc)
        print(f"User {Line_uid} migrated.")
        
# --- Step 3: Run Migration ---
if __name__ == "__main__":
    sqlite_data = export_sqlite("main.db")
    migrate_to_firestore(sqlite_data)
    print("✅ Migration complete")
