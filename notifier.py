from mcv_ import CVaScraper
from line_ import LineBot
from utility import *
import os
import pytz
from dotenv import load_dotenv

load_dotenv()
access_token = os.getenv("CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("CHANNEL_SECRET")
uid = os.getenv("LINE_ID")

def process_course_data(data: dict):
    """
    Processes the raw JSON data, extracts assignment information,
    and generates Flex Messages for each assignment.
    """
    # Get the current time in the local timezone (e.g., Asia/Bangkok for +07:00)
    # You can change 'Asia/Bangkok' to your desired timezone.
    current_time = datetime.now(pytz.timezone('Asia/Bangkok'))
    print(f"Current processing time (Asia/Bangkok): {current_time}\n")

    students_data = data.get('data', {}).get('me', {}).get('myCoursesBySemester', {}).get('student', [])

    if not students_data:
        print("No student data found in the provided JSON.")
        return

    messages = []
    for student_course in students_data:
        course_title = student_course.get('title', 'Unknown Course')
        course_id = student_course.get('courseID', 'N/A')
        assignments = student_course.get('assignments', [])

        if not assignments:
            print(f"No assignments found for course: {course_title}")
            continue

        print(f"--- Processing Course: {course_title} ({course_id}) ---")
        for assignment in assignments:
            assignment_name = assignment.get('title', 'Unknown Assignment')
            assignment_id = assignment.get('id', 'N/A')
            due_date_iso = assignment.get('dueDate', '')
            assignment_status = assignment.get('status', 'UNKNOWN')

            formatted_due_date = format_due_date(due_date_iso)
            time_left_str, total_seconds_left = calculate_time_left(due_date_iso, current_time)

            # Construct the detail URL
            detail_url = f"https://alpha.mycourseville.com/course/{course_id}/assignments/{assignment_id}"

            # Determine the state for create_flex_message
            # Based on the provided data, all assignments are 'OVERDUE'.
            # We'll map 'OVERDUE' status to 'not_submitted_overdue' for this example.
            # You can expand this logic for other statuses like 'SUBMITTED', etc.
            state = "not_submitted_normal" # Default state
            if assignment_status == "SUBMITTED":
                state = "submitted_on_time"
            elif assignment_status == "OVERDUE":
                state = "not_submitted_overdue"
            elif total_seconds_left <= 3600: # Less than 1 hour (critical)
                state = "not_submitted_critical"
            elif total_seconds_left < 172800: # Less than 2 days (warning)
                state = "not_submitted_warning"
            else: # More than 2 days
                state = "not_submitted_normal"

            course_info = {
                "course_title": course_title,
                "assignment_name": assignment_name,
                "due_date": formatted_due_date,
                "time_left": time_left_str,
                "detail_url": detail_url
            }

            flex_message = LineBot.create_flex_message(course_info, state)
            messages.append(flex_message)
    return messages

scraper = CVaScraper()
data = scraper.query_assignment(semester = 2, year = 2024, filter ="ALL")
# jdata = json2dict(data)

messages = process_course_data(data)
if messages:
    line_bot = LineBot(access_token, channel_secret)
    line_bot.push_noti_message(uid, messages[:5])
