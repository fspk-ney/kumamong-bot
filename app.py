import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv

# โหลดค่าจาก .env (ถ้ามี)
load_dotenv()

app = Flask(__name__)

# ดึงค่าจาก Environment Variables
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    
    # คำสั่งทดสอบพื้นฐาน
    if user_text == "เมี๊ยว":
        reply = "เรียกทำไมมนุษย์! จะออมเงินแล้วหรอ? 🐾"
    else:
        reply = f"คุ้มมงได้รับข้อความ '{user_text}' แล้วเมี๊ยว!"
        
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    # รันแบบ Local สำหรับเทส
    app.run(port=5000)