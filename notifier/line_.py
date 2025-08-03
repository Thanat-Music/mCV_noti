from Utility.utility import replace_placeholders
import json
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
)
from linebot.v3.messaging.models import FlexMessage, FlexContainer, PushMessageRequest


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
    def create_notify_message(bubble: dict, alt: str) -> FlexMessage:
        """
        Generates a Flex Message bubble for a course assignment notification by loading a JSON template
        and populating it with dynamic data based on the assignment's state.

        Args:
            bubble (dict): A flex message bubble like dictionary containing course and assignment information.
            alt (str): The alt text for the Flex Message, used as a fallback if the message cannot be rendered.

        Returns:
            FlexMessage: A FlexMessage object ready to be sent via the LINE Messaging API.
        """
        container = FlexContainer.from_dict(bubble)
        return FlexMessage(alt_text=alt, contents=container)

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