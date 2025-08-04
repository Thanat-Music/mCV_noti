from database.DB_manager import DBManager
from Utility.Cipher import cipher
from Utility.logger import info, warn, error

if __name__ == "__main__":
        db = DBManager()
        c = cipher()
        n = db.count_all_user()
        user_id = f"u{n+1}"
        cname = input("name")
        cpass = input("pass")
        line_uid = input("line")
        en_canme = c.encrypt(cname)
        en_cpass = c.encrypt(cpass)

        data = {"user_id":user_id,
                "cname":en_canme,
                "cpass":en_cpass,
                "Line_uid":line_uid
                }
        db.upsert_user(data)
        info("create_user", f"User {cname} created with ID {user_id}")
        db.commit()