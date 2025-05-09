import json
from flask import Flask, request
from linebot import LineBotApi
from linebot.models import TextSendMessage, ImageSendMessage
from linebot.exceptions import LineBotApiError


channel_acc_token = "lYZPXb044qOS9XLZB5vBtBHzym24Z7vj7fC0096L4Bi8iM84BEeJjQdpgW3EOW9nPV60wyOV8KO8JnuIaou4zZoQJkbUMm/whlSwg9Hqm5QbpNla9hEsnNM3UyZAaUoBzoRe8YqwrQyrfpgpv9VPrgdB04t89/1O/w1cDnyilFU="
line_bot_api = LineBotApi(channel_acc_token)


app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    response = request.get_json()
    if len(response['events'])>0:
        if response['events'][0]['message']['type']=="image":
            user_id = response['events'][0]['source']['userId']
            line_bot_api.push_message(user_id, TextSendMessage(text='อย่างไรก็ตามนี่เป็นกระเมิณผลเบื้องต้นเท่านั้น คุณควรปรึกษาผู้เชี่ยวชาญอีกครั้งเพื่อความมั่นใจ'))
    return json.dumps({'success':True}), 200, {'ContentType':'application/json'}
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)

