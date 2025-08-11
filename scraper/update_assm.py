import sqlite3
from scraper.scraper import CVaScraper
from datetime import datetime
from database.DB_manager import DBManager
from Utility.Cipher import cipher
from Utility.logger import info, error, warn

def parse_datetime(d):
    return datetime.fromisoformat(d.replace('Z', '+00:00')) if d else None

def get_semester_info():
    now = datetime.now()
    month = now.month
    year = now.year

    if 8 <= month <= 12:
        semester = 1
        academic_year = year
    elif 1 <= month <= 5:
        semester = 2
        academic_year = year - 1
    elif 6 <= month <= 7:
        semester = 3
        academic_year = year - 1
    else:
        raise ValueError("Invalid month for semester calculation.")

    return semester,academic_year
    
def get_assingment(cname,cpass):
    scraper = CVaScraper(username=cname, password=cpass, show=False)
    sem, aca_year = get_semester_info()
    # sem,aca_year = 1,2023
    data = scraper.query_assignment(sem, aca_year)
    return data["data"]["me"]["myCoursesBySemester"]["student"]
    
    

if __name__ == "__main__":
    db = DBManager()
    print(f"{datetime.now()}: Starting assignment update process...")
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect("database/main.db")
        cursor = conn.cursor()
        c = cipher()

        # Fetch users
        cursor.execute("SELECT user_id, cname, cpass FROM user")
        users = cursor.fetchall()

        for user_id, encname, encpass in users:
            cname = c.decrypt(encname)
            cpass = c.decrypt(encpass)
            try:
                assignments_data = get_assingment(cname,cpass)
                if not assignments_data:
                    warn("update_assm", f"NO data from mCV for user: {user_id}")
                    continue
            except Exception as e:
                error("update_assm", f"Error fetching from mCV {user_id}",e)
                continue
            for course in assignments_data:
                db.upsert_course(course)
                for a in course["assignments"]:
                    db.upsert_assignment(a)
                    db.assign_to_users(user_id,a["id"],a["status"])
        info("update_assm", "Assignments updated successfully")
    except sqlite3.Error as e:
        error("update_assm", f"SQLite error",e)
    except Exception as e:
        error("update_assm", f"Error during assignment update: {e}")
    finally:
        db.commit()
        db.close()
    
