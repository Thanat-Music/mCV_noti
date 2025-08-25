from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import os
import time
from dotenv import load_dotenv
from database.DB_manager import DBManager
from server.create_user import create_user
from Utility.logger import info, warn, error

load_dotenv()
access_token = os.getenv("CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("CHANNEL_SECRET")

app = Flask(__name__)

configuration = Configuration(access_token=access_token)
handler = WebhookHandler(channel_secret)

# sessions = {
#   line_uid: {
#       "step": 1,
#       "data": {"cname": "...", "cpass": "..."},
#       "last_active": timestamp
#   }
# }
sessions = {}
SESSION_TIMEOUT = 600  # 10 minutes in seconds


def is_session_expired(l_user_id):
    """Check if the session expired"""
    if l_user_id not in sessions:
        return True
    last_active = sessions[l_user_id]["last_active"]
    return time.time() - last_active > SESSION_TIMEOUT


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    l_user_id = event.source.user_id
    text = event.message.text.strip()
    reply_token = event.reply_token

    # Reset session if expired
    if l_user_id in sessions and is_session_expired(l_user_id):
        del sessions[l_user_id]
        reply(reply_token, "Session expired. Please start again by sending 'register'.")
        return

    # Handle cancel
    if text.lower() == "cancel":
        if l_user_id in sessions:
            del sessions[l_user_id]
            reply(reply_token, "Registration cancelled.")
        else:
            reply(reply_token, "No registration in progress.")
        return

    # Start registration
    if text.lower() == "register":
        db = DBManager()
        if db.is_line(l_user_id):  # Already registered
            reply(reply_token, "You are already registered.")
            db.close()
            return
        db.close()

        # Start new session
        sessions[l_user_id] = {
            "step": 1,
            "data": {},
            "last_active": time.time()
        }
        reply(reply_token, "Registration started. พิมพ์ cancel เพื่อยกเลิก \n อย่าลืมใช้ https://sparkly-narwhal-dbfc89.netlify.app/ เพื่อเข้ารหัสข้อมูลก่อนส่งเข้าแชท\n โปรดใส่ mCV username.")
        return

    # Continue registration if session exists
    if l_user_id in sessions:
        step = sessions[l_user_id]["step"]
        sessions[l_user_id]["last_active"] = time.time()

        # Step 1: Get username
        if step == 1:
            sessions[l_user_id]["data"]["cname"] = text
            sessions[l_user_id]["step"] = 2
            reply(reply_token, "โปรดใส่ mCV password.\n ใช้ https://sparkly-narwhal-dbfc89.netlify.app/ เพื่อเข้ารหัสข้อมูลก่อนส่งเข้าแชท")
            return

        # Step 2: Get password and create user
        elif step == 2:
            sessions[l_user_id]["data"]["cpass"] = text
            data = sessions[l_user_id]["data"]

            # Create user in DB
            uid = create_user(
                cname=data["cname"],
                cpass=data["cpass"],
                line_uid=l_user_id
            )

            reply(reply_token, "🎉 Registration successful! You can now use the service.")
            info("line_server", f"User {uid} registered with LINE ID {l_user_id}")
            del sessions[l_user_id]
            return

    # No registration in progress
    reply(reply_token, "Send 'register' to start the registration process.")


def reply(reply_token, text):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


if __name__ == "__main__":
    app.run()
