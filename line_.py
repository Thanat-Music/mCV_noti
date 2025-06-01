from utility import replace_placeholders
import json
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
)
from linebot.v3.messaging.models import FlexMessage, FlexContainer,PushMessageRequest


class LineBot:
    """
    A simple class to encapsulate LINE Messaging API functionality.
    This class can be extended with more methods as needed.
    """

    def __init__(self, access_token: str = None, channel_secret: str = None):
        token = access_token
        channel_secret = channel_secret
        self.configuration = Configuration(access_token=token)

    def push_noti_message(self,user_id: str, flex_messages: list):
        """
        Sends a Flex Message to a specific LINE user. This is suitable for proactive notifications.

        Args:
            user_id (str): The LINE user ID of the recipient.
            flex_messages (list): A list of FlexMessage objects to send.
        """

        if flex_messages is None:
            print("Flex Message is missing. Aborting send.")
            return

        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            try:
                # Use push_message for proactive notifications from your project
                request = PushMessageRequest(to=user_id, messages=flex_messages)
                line_bot_api.push_message(request)
            except Exception as e:
                print(f"Failed to send Flex Message: {e}")

    # --- Flex Message Generation Function ---
    @staticmethod
    def create_flex_message(course_info: dict, state: str) -> FlexMessage:
        """
        Generates a Flex Message bubble for a course assignment notification by loading a JSON template
        and populating it with dynamic data based on the assignment's state.

        Args:
            course_info (dict): A dictionary containing assignment details.
                Expected keys:
                - "course_title": str (e.g., "COMPUTER PROGRAMMING")
                - "assignment_name": str (e.g., "Sec 4: In-class 1")
                - "due_date": str (e.g., "23 Jan 2025 at 23:59")
                - "time_left": str (e.g., "1 day 20 hour", "Overdue", "23 hour", "51 min")
                - "detail_url": str (e.g., "https://alpha.mycourseville.com/course/0000-Mar/assignments/oER2-ANLA")
            state (str): The state of the assignment, determining the appearance and text.
                Expected values (case-sensitive):
                - "submitted_on_time"
                - "submitted_overdue"
                - "not_submitted_normal"
                - "not_submitted_warning"
                - "not_submitted_critical"
                - "not_submitted_overdue"

        Returns:
            FlexMessage: A FlexMessage object ready to be sent via the LINE Messaging API.
        """

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

        # Combine course_info and state_properties for easy formatting
        # Ensure all expected placeholders are present in the combined dictionary
        template_data = {
            "COURSE_TITLE": course_info.get("course_title", "N/A"),
            "ASSIGNMENT_NAME": course_info.get("assignment_name", "N/A"),
            "DUE_DATE": course_info.get("due_date", "N/A"),
            "TIME_LEFT": course_info.get("time_left", "N/A"),
            "DETAIL_URL": course_info.get("detail_url", "https://www.mycourseville.com/"),
            **props # Unpack state-specific properties
        }

        # Load the Flex Message JSON template from file
        try:
            with open('flex_template.json', 'r', encoding='utf-8') as f:
                flex_template = f.read()
        except FileNotFoundError:
            print("Error: 'course_notification_bubble_template.json' not found. Please create the file.")
        except json.JSONDecodeError:
            print("Error: 'course_notification_bubble_template.json' contains invalid JSON.")
            
        formatted_flex_json = replace_placeholders(flex_template, template_data)
        # Deserialize the formatted JSON string into a FlexContainer object
        bubble_container = FlexContainer.from_json(formatted_flex_json)

        # The alt_text is a fallback text displayed if the Flex Message cannot be rendered on the user's device.
        return FlexMessage(alt_text=f"Course Noti: {course_info['assignment_name']} - Status: {state} - Due in {course_info['time_left']}", contents=bubble_container)

if __name__ == "__main__":
    course_info = {
            "course_title": "COMPUTER PROGRAMMING",
            "assignment_name": "In-class 1: Basic Syntax",
            "due_date": "23 Jan 2025 at 23:59",
            "time_left": "1 day 20 hour",
            "detail_url": "https://alpha.mycourseville.com/course/0000-Mar/assignments/oER2-ANLA"
        }
    state = "not_submitted_critical"
    print(LineBot.create_flex_message(course_info, state))