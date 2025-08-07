import sqlite3


class DBManager:
    def __init__(self, db_name="database/main.db"):
        self.conn = sqlite3.connect(db_name)
        self.cur = self.conn.cursor()

    def upsert_course(self, course):
        self.cur.execute("""
            INSERT OR IGNORE INTO course (course_id, name, courseNumber, thumbnail, semester)
            VALUES (?, ?, ?, ?, ?)
        """, (
            course["courseID"],
            course["title"],
            course["courseNumber"],
            course["thumbnail"],
            course["semester"]
        ))

    def upsert_assignment(self, assignment):
        self.cur.execute("""
            INSERT INTO assignment (assignment_id, course_id, due_date, name, type)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(assignment_id) DO UPDATE SET
                course_id=excluded.course_id,
                due_date=excluded.due_date,
                name=excluded.name,
                type=excluded.type;
        """, (
            assignment["id"],
            assignment["courseID"],
            assignment["dueDate"],
            assignment["title"],
            assignment["type"]
        ))

    def upsert_user(self, data):
        self.cur.execute("""
            INSERT INTO user (user_id, cname, cpass, Line_uid)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                cname=excluded.cname,
                cpass=excluded.cpass,
                Line_uid=excluded.Line_uid
        """, (
            data["user_id"],
            data["cname"],
            data["cpass"],
            data["Line_uid"]
        ))
        
    def delete_user(self,user_id):
        self.cur.execute("""
            DELETE FROM user WHERE user_id = ?;
        """, (user_id,))

    def assign_to_users(self,user_id, assignment_id,status):
        self.cur.execute("""
            INSERT OR IGNORE INTO user_assignments (user_id, assignment_id, notify_3d, notify_1d,status)
            VALUES (?, ?, FALSE, FALSE,?);
        """, (user_id, assignment_id,status))
        
    def count_all_user(self):
        self.cur.execute("SELECT COUNT(*) FROM user;")
        count = self.cur.fetchone()[0]
        return count
    
    def fetch_all_notify_data_all(self):
        self.cur.execute("""
            SELECT u.line_uid, c.course_id, c.name AS course_name, c.courseNumber, c.thumbnail, c.semester,
                   a.assignment_id, a.name AS assignment_name, a.due_date, a.type, ua.status
            FROM user_assignments ua
            JOIN user u ON ua.user_id = u.user_id
            JOIN assignment a ON ua.assignment_id = a.assignment_id
            JOIN course c ON a.course_id = c.course_id
            WHERE a.due_date IS NOT NULL
            ORDER BY u.line_uid, c.course_id, a.due_date;
        """)
        return self.cur.fetchall()

    def fetch_assignments_by_user(self, user_id):
        query = """
        SELECT 
            ua.user_id,
            a.assignment_id,
            a.name AS assignment_name,
            a.due_date,
            a.type AS assignment_type,
            ua.status,
            c.course_id,
            c.name AS course_name,
            c.courseNumber,
            c.thumbnail,
            c.semester,
            ua."1d",
            ua."3d"
        FROM user_assignments ua
        JOIN assignments a ON ua.assignment_id = a.assignment_id
        JOIN course c ON a.course_id = c.course_id
        WHERE ua.user_id = ?
        """
        self.cur.execute(query, (user_id,))
        return self.cur.fetchall()
    
    def fetch_open_assm_by_id(self, user_id):
        query = """
            SELECT 
                a.assignment_id,
                a.name AS assignment_name,
                a.due_date,
                a.type AS assignment_type,
                ua.status,
                c.course_id,
                c.name AS course_name,
                c.courseNumber,
                c.thumbnail,
                c.semester
            FROM user_assignments ua
            JOIN assignment a ON ua.assignment_id = a.assignment_id
            JOIN course c ON a.course_id = c.course_id
            WHERE 
                datetime(a.due_date) >= datetime('now', '+7 hours')
                AND datetime(a.due_date) <= datetime('now', '+7 days', '+7 hours')
                AND ua.user_id = ?;
        """
        self.cur.execute(query,(user_id,))
        return self.cur.fetchall()
    
    def fetch_notify_user(self):
        query = """
            SELECT 
                ua.user_id,
                u.Line_uid,
                ua.notify_3d,
                ua.notify_1d,
                a.assignment_id
            FROM user_assignments ua
            JOIN assignment a ON ua.assignment_id = a.assignment_id
            JOIN user u ON ua.user_id = u.user_id
            WHERE 
                datetime(a.due_date) >= datetime('now', '+7 hours')
                AND datetime(a.due_date) <= datetime('now', '+3 days', '+7 hours')
                AND (ua.notify_3d = FALSE OR ua.notify_1d = FALSE);
        """
        self.cur.execute(query)
        return self.cur.fetchall()
    
    def Update_notify(self, user_id, assignment_id, notify_3d, notify_1d):
        self.cur.execute("""
            UPDATE user_assignments
            SET notify_3d = ?, notify_1d = ?
            WHERE user_id = ? AND assignment_id = ?;
        """, (notify_3d, notify_1d, user_id, assignment_id))
        return self.cur.rowcount > 0

    
    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()
        
if __name__ == "__main__":
    db = DBManager()
    # command = input()
    # db.delete_user("u1")
    # while command != "quit":
    #     exec(command)
    #     command = input()
    db.commit()
    db.close()
    
# db.delete_user("u1")
