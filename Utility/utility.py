from datetime import datetime, timezone
import re
import json

def format_due_date(iso_date_str: str) -> str:
    """
    Formats an ISO 8601 date string to "DD MonYYYY at HH:MM".

    Args:
        iso_date_str (str): The date string in ISO 8601 format (e.g., "2023-11-10T23:59:00+07:00").

    Returns:
        str: Formatted date string or "N/A" if parsing fails.
    """
    try:
        # Parse the ISO 8601 string directly. datetime.fromisoformat handles timezone.
        dt_object = datetime.fromisoformat(iso_date_str)
        # Format to "DD MonYYYY at HH:MM"
        return dt_object.strftime("%d %b %Y at %H:%M")
    except ValueError:
        return "N/A"

def calculate_time_left(due_date_str: str, current_time: datetime) -> tuple[str, int | None]:
    """
    Calculates the time remaining until a due date or returns "Overdue".
    Displays only the most significant time unit based on proximity to due date.

    Args:
        due_date_str (str): The due date string in ISO 8601 format.
        current_time (datetime): The current datetime object, preferably timezone-aware.

    Returns:
        tuple[str, float | None]: A tuple containing:
            - str: Formatted string indicating time left (e.g., "1 day 20 hours", "Overdue", "51 mins").
            - float | None: Total seconds remaining, or -1 for "Overdue", or None for error.
    """
    try:
        due_dt = datetime.fromisoformat(due_date_str)

        # Ensure both datetimes are timezone-aware and comparable.
        if due_dt.tzinfo is None:
            # If due_dt is naive, assume it's in the same timezone as current_time or UTC.
            pass # fromisoformat handles the +07:00 offset if present

        if current_time.tzinfo is None:
            # If current_time is naive, assume it's local and make it timezone-aware
            current_time = current_time.replace(tzinfo=timezone.utc)

        # Convert both to UTC for safe comparison
        due_dt_utc = due_dt.astimezone(timezone.utc)
        current_time_utc = current_time.astimezone(timezone.utc)

        time_diff = due_dt_utc - current_time_utc

        if time_diff.total_seconds() < 0:
            return "Overdue", -1.0
        else:
            total_seconds = time_diff.total_seconds()
            days = time_diff.days
            hours = time_diff.seconds // 3600
            minutes = (time_diff.seconds % 3600) // 60

            formatted_string = ""
            # Logic for significant time amounts
            # Logic for significant time amounts
            if total_seconds < 60: # Less than a minute
                formatted_string = "Less than a minute"
            elif days > 2: # More than 2 days, show only days
                formatted_string = f"{days} day{'s' if days > 1 else ''}"
            elif days > 0: # 1 or 2 days, show days and hours
                formatted_string = f"{days} day{'s' if days > 1 else ''} {hours} hour{'s' if hours > 1 else ''}"
            elif hours > 6: # More than 6 hours (but less than 1 day), show hours
                formatted_string = f"{hours} hour{'s' if hours > 1 else ''}"
            elif hours > 0: # 1 to 6 hours, show hours and minutes
                formatted_string = f"{hours} hour{'s' if hours > 1 else ''} {minutes} min{'s' if minutes > 1 else ''}"
            elif minutes > 1: # If less than 1 hour, show only minutes
                formatted_string = f"{minutes} min{'s' if minutes > 1 else ''}"
            else: # If less than 1 minute, return a specific message
                formatted_string = "less than a minute"
            return formatted_string, total_seconds
    except ValueError as e:
        print(f"Error calculating time left for {due_date_str}: {e}")
        return "N/A", None
      
def replace_placeholders(json_string: str, values: dict) -> str:
    """    Replaces placeholders in a JSON string with corresponding values from a dictionary.
    This function searches for placeholders in the format <KEY> within the JSON string

    Args:
        json_string (str): The JSON string containing placeholders to be replaced.
        values (dict): A dictionary containing key-value pairs where keys correspond to placeholders in the JSON string.

    Returns:
        str: The JSON string with placeholders replaced by their corresponding values.
    """
    # Match placeholders like <TITLE>
    pattern = re.compile(r'<(.*?)>')
    
    def replacer(match):
        key = match.group(1)
        return values.get(key, match.group(0))  # Keep original if key not found
    
    return pattern.sub(replacer, json_string)

def json2dict(json_string: str) -> dict:
    """
    Converts a JSON string to a Python dictionary.

    Args:
        json_string (str): The JSON string to convert.

    Returns:
        dict: The converted dictionary.
    """
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return {}
    
def read_json_file_str(file_path: str) -> str:
    """
    Reads a JSON file and returns its content as a string.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        str: The content of the JSON file as a string.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return ""
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return ""

def get_assignment_state(assignment_status: str, total_seconds_left: int) -> str:
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
    elif total_seconds_left <= 90000:  # Less than 1 hour (critical)
        return "not_submitted_critical"
    elif total_seconds_left <= 265000:  # Less than 2 days (warning)
        return "not_submitted_warning"
    else:  # More than 2 days
        return "not_submitted_normal"

