from database.DB_manager import DBManager
from Utility.Cipher import cipher
from Utility.logger import info, warn, error

def create_user(cname, cpass, line_uid):
        db = DBManager()
        n = db.count_all_user()
        user_id = f"u{n+1}"
        data = {"user_id":user_id,
                "cname":cname,
                "cpass":cpass,
                "Line_uid":line_uid
                }
        db.upsert_user(data)
        info("create_user", f"User {cname} created with ID {user_id}")
        db.commit()
        db.close()
        return user_id
        
if __name__ == "__main__":
        c = cipher()
        cname = input("Enter your name: ")
        cpass = input("Enter your password: ")
        en_canme = c.encrypt(cname)
        en_cpass = c.encrypt(cpass)
        line_uid = input("Enter your LINE user ID: ")
        create_user(cname, cpass, line_uid)