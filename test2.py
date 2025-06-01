def process_course_data(data: dict):
    """
    Processes the raw JSON data, extracts assignment information,
    and generates a single grouped Flex Message for all courses and assignments.
    """
    # Get the current time in the local timezone (e.g., Asia/Bangkok for +07:00)
    current_time = datetime.now(pytz.timezone('Asia/Bangkok'))
    print(f"Current processing time (Asia/Bangkok): {current_time}\n")

    students_data = data.get('data', {}).get('me', {}).get('myCoursesBySemester', {}).get('student', [])

    if not students_data:
        print("No student data found in the provided JSON.")
        return []

    # Dictionary to group assignments by course
    assignments_by_course = {}
    
    for student_course in students_data:
        course_title = student_course.get('title', 'Unknown Course')
        course_id = student_course.get('courseID', 'N/A')
        assignments = student_course.get('assignments', [])

        if not assignments:
            print(f"No assignments found for course: {course_title}")
            continue

        print(f"--- Processing Course: {course_title} ({course_id}) ---")
        
        # Initialize course in the dictionary if not exists
        if course_title not in assignments_by_course:
            assignments_by_course[course_title] = []
        
        for assignment in assignments:
            assignment_name = assignment.get('title', 'Unknown Assignment')
            assignment_id = assignment.get('id', 'N/A')
            due_date_iso = assignment.get('dueDate', '')
            assignment_status = assignment.get('status', 'UNKNOWN')

            formatted_due_date = format_due_date(due_date_iso)
            time_left_str, total_seconds_left = calculate_time_left(due_date_iso, current_time)

            # Construct the detail URL
            detail_url = f"https://alpha.mycourseville.com/course/{course_id}/assignments/{assignment_id}"

            # Determine the state
            state = determine_assignment_state(assignment_status, total_seconds_left)

            # Create assignment entry for grouped structure
            assignment_entry = {
                "assignment_name": assignment_name,
                "due_date": formatted_due_date,
                "time_left": time_left_str,
                "detail_url": detail_url,
                "state": state
            }
            
            assignments_by_course[course_title].append(assignment_entry)
            
            print(f"  Assignment: {assignment_name} - State: {state} - Due: {formatted_due_date}")

    # Create the grouped flex message if we have any assignments
    if assignments_by_course:
        flex_message = LineBot.create_grouped_flex_message(assignments_by_course)
        return [flex_message] if flex_message else []
    else:
        print("No assignments found in any course.")
        return []


def determine_assignment_state(assignment_status: str, total_seconds_left: int) -> str:
    """
    Determines the assignment state based on status and time left.
    
    Args:
        assignment_status (str): Status from the API (e.g., 'SUBMITTED', 'OVERDUE', etc.)
        total_seconds_left (int): Seconds remaining until due date
        
    Returns:
        str: State identifier for styling
    """
    if assignment_status == "SUBMITTED":
        return "submitted_on_time"
    elif assignment_status == "OVERDUE":
        return "not_submitted_overdue"
    elif total_seconds_left <= 0:  # Past due date but not marked as overdue yet
        return "not_submitted_overdue"
    elif total_seconds_left <= 3600:  # Less than 1 hour (critical)
        return "not_submitted_critical"
    elif total_seconds_left <= 172800:  # Less than 2 days (warning)
        return "not_submitted_warning"
    else:  # More than 2 days
        return "not_submitted_normal"


def process_course_data_individual(data: dict):
    """
    Alternative function that maintains the original individual message approach.
    Use this if you want to keep the old behavior alongside the new grouped approach.
    """
    current_time = datetime.now(pytz.timezone('Asia/Bangkok'))
    print(f"Current processing time (Asia/Bangkok): {current_time}\n")

    students_data = data.get('data', {}).get('me', {}).get('myCoursesBySemester', {}).get('student', [])

    if not students_data:
        print("No student data found in the provided JSON.")
        return []

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

            # Determine the state
            state = determine_assignment_state(assignment_status, total_seconds_left)

            course_info = {
                "course_title": course_title,
                "assignment_name": assignment_name,
                "due_date": formatted_due_date,
                "time_left": time_left_str,
                "detail_url": detail_url
            }

            # Use the original individual message creation
            flex_message = LineBot.create_flex_message(course_info, state)
            messages.append(flex_message)
    
    return messages


def convert_individual_to_grouped(individual_assignments_data: list) -> dict:
    """
    Helper function to convert data from individual assignment format to grouped format.
    Useful if you have existing individual assignment data that you want to group.
    
    Args:
        individual_assignments_data: List of dictionaries with course_info and state
        
    Returns:
        dict: Grouped assignments by course title
    """
    grouped = {}
    
    for item in individual_assignments_data:
        course_info = item.get("course_info", {})
        state = item.get("state", "not_submitted_normal")
        
        course_title = course_info.get("course_title", "Unknown Course")
        
        if course_title not in grouped:
            grouped[course_title] = []
        
        assignment_entry = {
            "assignment_name": course_info.get("assignment_name", "N/A"),
            "due_date": course_info.get("due_date", "N/A"),
            "time_left": course_info.get("time_left", "N/A"),
            "detail_url": course_info.get("detail_url", "https://www.mycourseville.com/"),
            "state": state
        }
        
        grouped[course_title].append(assignment_entry)
    
    return grouped


# Example usage:
"""
# For grouped messages (new approach):
messages = process_course_data(your_json_data)

# For individual messages (original approach):
messages = process_course_data_individual(your_json_data)

# To convert existing individual data to grouped:
individual_data = [
    {
        "course_info": {"course_title": "MATH", "assignment_name": "Quiz 1", ...},
        "state": "not_submitted_warning"
    },
    # ... more individual assignments
]
grouped_data = convert_individual_to_grouped(individual_data)
grouped_message = LineBot.create_grouped_flex_message(grouped_data)
"""