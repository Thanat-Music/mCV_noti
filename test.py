def create_grouped_flex_message(assignments_by_course: dict) -> FlexMessage:
    """
    Generates a Flex Message with grouped assignments by course using separate header and body templates.
    Creates a carousel of bubbles, one for each course.
    
    Args:
        assignments_by_course (dict): A dictionary where keys are course titles and values are lists of assignments.
            Structure:
            {
                "COMPUTER PROGRAMMING": [
                    {
                        "assignment_name": "Sec 4: In-class 1",
                        "due_date": "23 Jan 2025 at 23:59",
                        "time_left": "1 day 20 hour",
                        "detail_url": "https://alpha.mycourseville.com/course/0000-Mar/assignments/oER2-ANLA",
                        "state": "not_submitted_warning"
                    },
                    # ... more assignments
                ],
                # ... more courses
            }
    
    Returns:
        FlexMessage: A FlexMessage object ready to be sent via the LINE Messaging API.
    """
    
    # Define properties for each state
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
    
    # Load the course bubble template
    try:
        with open('flex_course_template.json', 'r', encoding='utf-8') as f:
            course_template = f.read()
        with open('flex_assignment_body.json', 'r', encoding='utf-8') as f:
            assignment_body_template = f.read()
    except FileNotFoundError as e:
        print(f"Error: Template file not found - {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in template file - {e}")
        return None
    
    # Build carousel bubbles - one bubble per course
    course_bubbles = []
    
    for course_title, assignments in assignments_by_course.items():
        # Create assignment body sections for this course
        assignment_contents = []
        
        for assignment in assignments:
            state = assignment.get("state", "not_submitted_normal")
            props = state_properties.get(state, state_properties["not_submitted_normal"])
            
            assignment_data = {
                "ASSIGNMENT_NAME": assignment.get("assignment_name", "N/A"),
                "DUE_DATE": assignment.get("due_date", "N/A"),
                "TIME_LEFT": assignment.get("time_left", "N/A"),
                "DETAIL_URL": assignment.get("detail_url", "https://www.mycourseville.com/"),
                **props
            }
            
            formatted_assignment = replace_placeholders(assignment_body_template, assignment_data)
            try:
                assignment_json = json.loads(formatted_assignment)
                assignment_contents.append(assignment_json)
            except json.JSONDecodeError as e:
                print(f"Error parsing assignment JSON: {e}")
                continue
        
        # Create the course bubble with header and assignment contents
        course_data = {
            "COURSE_TITLE": course_title
        }
        formatted_course_bubble = replace_placeholders(course_template, course_data)
        
        try:
            course_bubble = json.loads(formatted_course_bubble)
            # Replace the single assignment body with multiple assignments
            course_bubble["body"]["contents"] = assignment_contents
            course_bubbles.append(course_bubble)
        except json.JSONDecodeError as e:
            print(f"Error parsing course bubble JSON: {e}")
            continue
    
    # Create carousel or single bubble based on number of courses
    if len(course_bubbles) == 1:
        final_container = course_bubbles[0]
    else:
        final_container = {
            "type": "carousel",
            "contents": course_bubbles
        }
    
    # Deserialize into FlexContainer object
    try:
        final_flex_json = json.dumps(final_container)
        bubble_container = FlexContainer.from_json(final_flex_json)
    except Exception as e:
        print(f"Error creating FlexContainer: {e}")
        return None
    
    # Generate alt text
    total_assignments = sum(len(assignments) for assignments in assignments_by_course.values())
    course_count = len(assignments_by_course)
    alt_text = f"Course Notifications: {course_count} courses, {total_assignments} assignments"
    
    return FlexMessage(alt_text=alt_text, contents=bubble_container)


# Helper function to group existing individual assignments by course
def group_assignments_by_course(individual_assignments: list) -> dict:
    """
    Groups individual assignment dictionaries by course title.
    
    Args:
        individual_assignments (list): List of assignment dictionaries, each containing course_info and state
            Example:
            [
                {
                    "course_info": {
                        "course_title": "COMPUTER PROGRAMMING",
                        "assignment_name": "Sec 4: In-class 1",
                        "due_date": "23 Jan 2025 at 23:59",
                        "time_left": "1 day 20 hour",
                        "detail_url": "https://alpha.mycourseville.com/..."
                    },
                    "state": "not_submitted_warning"
                },
                # ... more assignments
            ]
    
    Returns:
        dict: Grouped assignments by course title
    """
    grouped = {}
    
    for assignment_data in individual_assignments:
        course_info = assignment_data.get("course_info", {})
        state = assignment_data.get("state", "not_submitted_normal")
        
        course_title = course_info.get("course_title", "Unknown Course")
        
        if course_title not in grouped:
            grouped[course_title] = []
        
        # Create assignment entry for the grouped structure
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
# If you have existing individual assignments:
individual_assignments = [
    {
        "course_info": {
            "course_title": "COMPUTER PROGRAMMING",
            "assignment_name": "Sec 4: In-class 1",
            "due_date": "23 Jan 2025 at 23:59",
            "time_left": "1 day 20 hour",
            "detail_url": "https://alpha.mycourseville.com/..."
        },
        "state": "not_submitted_warning"
    },
    # ... more assignments
]

# Group them by course
grouped_assignments = group_assignments_by_course(individual_assignments)

# Create the grouped flex message
flex_message = create_grouped_flex_message(grouped_assignments)
"""