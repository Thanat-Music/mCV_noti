from database.DB_manager import DBManager
from notifier.line_ import LineBot
from Utility.utility import *
from Utility.logger import info, warn, error
import os
import pytz
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
access_token = os.getenv("CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("CHANNEL_SECRET")

def get_notify_user(db: DBManager) -> dict:
    """
    Fetches user id for notifications from the database.
    
    Args:
        db (DBManager): The database manager instance.
        
    Returns:
        dict: A dictionary containing user IDs and their corresponding assignment data.
    """
    data = dict()
    rows_3day = db.fetch_3d_notify_user()
    for row in rows_3day:
        user_id,Line_uid, assignment_id = row
        if user_id not in data:
            data[user_id] = {"l":Line_uid,"d1": [], "d3": []}
        data[user_id]["d3"].append(assignment_id)
    rows_1day = db.fetch_1d_notify_user()
    for row in rows_1day:
        user_id, Line_uid, assignment_id = row
        if user_id not in data:
            data[user_id] = {"l": Line_uid, "d1": [], "d3": []}
        data[user_id]["d1"].append(assignment_id)

    return data

def fetch_assignment_data(db: DBManager, uid: str) -> list[dict]:
    rows = db.fetch_open_assm_by_id(uid)

    courses = {}  # Key: course_id, Value: course dict

    for row in rows:
        (
        assignment_id, assignment_name, due_date, a_type, status,
        course_id, course_name, course_number, thumbnail, semester
        ) = row

        if course_id not in courses:
            courses[course_id] = {
                "courseID": course_id,
                "title": course_name,
                "courseNumber": course_number,
                "thumbnail": thumbnail,
                "semester": semester,
                "assignments": []
            }

        courses[course_id]["assignments"].append({
            "courseID": course_id,
            "id": assignment_id,
            "title": assignment_name,
            "type": a_type,
            "status": status,
            "dueDate": due_date
        })

    return list(courses.values())

def process_course_data(course_list: list):
    """
    Processes the raw JSON data, extracts assignment information,
    and generates Flex Messages for each assignment.
    
    """
    messages = []
    for course in course_list:
        course_data = {
                "title": course.get('title', 'Unknown Course'),
                "courseID": course.get('courseID', 'Unknown Course'),
                "assignments": course.get('assignments', []),
                "semester": course.get('semester', 'N/A'),
                "courseNumber": course.get('courseNumber', 'N/A')
            }
        if len(course_data["assignments"]) == 0:
            continue
        try:
            message = create_crouse_flex_bubble(course_data)
            if message:
                bubble, alt = message
                flex_message = LineBot.create_notify_message(bubble, alt)
                messages.append(flex_message)
        except Exception as e:
            error("notify_engine",f"Failed to create Flex Message for course: {course_data['title']}. Error: {e}")


    return messages

def create_assingment_flex_body(assignment_info: dict) -> dict:
    """
    Creates a Flex Message for a single assignment.
    
    Args:
        course_info (dict): Information about the course and assignment.
        
    Returns:
        body_content (dict): The Flex Message structure.
    """
    # Load the Flex Message template
    template_path = 'notifier/flex_body_template.json'
    
    # -------------------------------- Check time left --------------------------------------------------------------------------
    current_time = datetime.now(pytz.timezone('Asia/Bangkok'))
    due_date = assignment_info.get('dueDate', '')
    time_left_str, total_seconds_left = calculate_time_left(due_date, current_time)
    # get the state of the assignment
    state = get_assignment_state(assignment_info.get('status', 'UNKNOWN'), total_seconds_left)
    # Define properties for each state, including text, colors, and font styles
    state_properties = {
        "submitted_on_time": {
            "STATUS_TEXT": "Submitted",
            "STATUS_BG_COLOR": "#22c55e", # Green
            "TIME_LEFT_COLOR": "#2d3138", # Dark gray
            "TIME_LEFT_WEIGHT": "regular",
            "TIME_LEFT_SIZE": "md"
        },
         "submitted_overdue": {
            "STATUS_TEXT": "Submitted",
            "STATUS_BG_COLOR": "#22c55e", # Green
            "TIME_LEFT_COLOR": "#750060", # Purple
            "TIME_LEFT_WEIGHT": "bold",
            "TIME_LEFT_SIZE": "lg"
        },
        "not_submitted_normal": {
            "STATUS_TEXT": "Not submitted",
            "STATUS_BG_COLOR": "#94a3b8", # Light gray/blue
            "TIME_LEFT_COLOR": "#2d3138", # Dark gray
            "TIME_LEFT_WEIGHT": "regular",
            "TIME_LEFT_SIZE": "md"
        },
        "not_submitted_warning": {
            "STATUS_TEXT": "Not submitted",
            "STATUS_BG_COLOR": "#fab002", # Orange/Yellow
            "TIME_LEFT_COLOR": "#fab002", # Orange/Yellow
            "TIME_LEFT_WEIGHT": "bold",
            "TIME_LEFT_SIZE": "xl"
        },
        "not_submitted_critical": {
            "STATUS_TEXT": "Not submitted",
            "STATUS_BG_COLOR": "#ef4444", # Red
            "TIME_LEFT_COLOR": "#ef4444", # Red
            "TIME_LEFT_WEIGHT": "bold",
            "TIME_LEFT_SIZE": "3xl"
        },
        "not_submitted_overdue": {
            "STATUS_TEXT": "Not submitted",
            "STATUS_BG_COLOR": "#574353", # Dark purple/gray
            "TIME_LEFT_COLOR": "#750060", # Purple
            "TIME_LEFT_WEIGHT": "bold",
            "TIME_LEFT_SIZE": "lg"
        }
    }
    
    # Get the properties for the requested state, default to 'not_submitted_normal' if state is unknown
    props = state_properties.get(state, state_properties["not_submitted_normal"])
    #----------------------------------------------------------------------------------------------------------------------------


    # ------------------- Combine course_info and state_properties for easy formatting ------------------------------------------
    # Ensure all expected placeholders are present in the combined dictionary
    template_data = {
        "ASSIGNMENT_NAME": assignment_info.get("title", "N/A"),
        "DUE_DATE": assignment_info.get("dueDate", "N/A"),
        "TIME_LEFT": time_left_str,
        "DETAIL_URL": f"https://alpha.mycourseville.com/course/{assignment_info['courseID']}/assignments/{assignment_info['id']}",
        **props # Unpack state-specific properties
    }
    with open(template_path, 'r', encoding='utf-8') as file:
        body_template = file.read()
    body_content = replace_placeholders(body_template, template_data)
    body_content = json.loads(body_content)  # Convert string to JSON object
    #----------------------------------------------------------------------------------------------------------------------------
    
    return body_content

def create_crouse_flex_bubble(course_data: dict) ->  tuple[dict,str]:
    """
    Creates a Flex Bubble for a course with its assignments.
    
    Args:
        corse_data (dict): Information about the course and its assignments.
        
    Returns:
        bubble (dict): The Flex Bubble structure.
        alt (str): The alt text for the Flex Message.
        
    """
    # Load the Flex Bubble template
    template_path = 'notifier/flex_header_template.json'
    with open(template_path, 'r', encoding='utf-8') as file:
        header_template = file.read()
    course_info = {
        "COURSE_TITLE": course_data.get("title", "N/A")
    }
    bubble_template = replace_placeholders(header_template, course_info)
    bubble = json.loads(bubble_template)
    assignments = course_data.get("assignments", [])
    # Create the Flex Message body for the assignment
    body_contents = []
    if len(assignments) == 0:
        return {}, "No assignments found"
    
    for assignment in assignments:
        body_cont = create_assingment_flex_body(assignment_info=assignment)
        body_contents.append(body_cont)
    # Add the body contents to the bubble
    bubble['body']['contents'] = body_contents
    # Create the alt text for the Flex Message
    alt = f"Course: {course_data.get('title', 'N/A')} - Assignments: {len(assignments)}"


    return bubble,alt

if __name__ == "__main__":
    print(f"{datetime.now()}: Starting notification engine")
    db = DBManager()
    try: 
        users = get_notify_user(db)
        if not users:
            info("notify_engine","No users found for notifications.")
            exit(0)
    except Exception as e:
        error("notify_engine",f"Failed to fetch notify users: {e}")
        exit(1)
        
    for uid in users:
        try:
            assignment_data = fetch_assignment_data(db, uid)
        except Exception as e:
            error("notify_engine", f"Failed to fetch assignment from DB for user {uid}", e)
            continue
        if assignment_data:
            try:
                messages = process_course_data(assignment_data)
            except Exception as e:
                error("notify_engine", f"Failed to create message for {uid}", e)
                continue
            try:
                if messages:
                    line_bot = LineBot(access_token, channel_secret)
                    for i in range(0,len(messages),5):
                        # Send messages in batches of 5
                        line_bot.push_noti_message(users[uid]['l'], messages[i:i+5])
                else:
                    warn("notify_engine", f"No valid messages to send for user: {uid}")
                info("notify_engine", f"Send {len(messages)} messages to user: {uid}")
            except Exception as e:
                error("notify_engine", f"Failed to send message to user {uid}", {e})
                continue
        for assignment_id in users[uid]["d3"]:
            db.Update_notify(uid, assignment_id, True, False)
            info("notify_engine", f"Updated 3-day noti for user: {uid}, assignment: {assignment_id}")
        for assignment_id in users[uid]["d1"]:
            db.Update_notify(uid, assignment_id, True, True)
            info("notify_engine", f"Updated 1-day noti for user: {uid}, assignment: {assignment_id}")
        else:
            info("notify_engine", f"No upcoming assignment found for user: {uid}")
    db.commit()
    db.close()
    info("notify_engine", "Notification engine finished processing.")