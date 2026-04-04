import os
from flask import Flask, request, abort, send_from_directory # เพิ่ม send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- ส่วนที่เพิ่มมาเพื่อให้เข้าหน้า index.html ได้ ---
@app.route('/')
@app.route('/index.html')
def serve_index():
    return send_from_directory('.', 'index.html')
# ----------------------------------------------

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
    text = event.message.text
    
    if "[คำสั่งออมเงิน]" in text:
        try:
            lines = text.split('\n')
            goal_name = lines[1].split(': ')[1]
            total = float(lines[2].split(': ')[1])
            freq = lines[3].split(': ')[1]
            per_installment = round((total / 2) / 36, 2)
            
            reply_text = (
                f"🐾 คุ้มมงเปิดบิลออมเงินแล้วเมี๊ยว!\n\n"
                f"📌 เป้าหมาย: {goal_name}\n"
                f"💰 ยอดรวม: {total:,.2f} บาท\n"
                f"⏰ ความถี่: {freq}\n"
                f"🔢 ทั้งหมด: 36 งวด\n"
                f"----------------------\n"
                f"💵 เก็บคนละประมาณ: {per_installment:,.2f} บาท/งวด\n"
                f"(คำนวณสำหรับสมาชิก 2 คน)\n\n"
                f"เตรียมเงินไว้ให้ดี อย่าให้คุ้มมงต้องกางเล็บ! 🐱"
            )
        except:
            reply_text = "ข้อมูลไม่ถูกต้อง ลองตั้งค่าใหม่อีกทีนะเฮีย"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    elif text == "สร้างบิล":
        liff_url = "https://liff.line.me/2009693749-SfmWsP0l"
        reply_text = f"จิ้มที่ลิงก์เพื่อตั้งค่าบิลออมเงินเลยเมี๊ยว! 🐾\n{liff_url}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(port=5000)