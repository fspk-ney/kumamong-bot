import os
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    FlexSendMessage, PostbackEvent
)
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ตั้งค่า LINE
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# ตั้งค่า Supabase
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

@app.route('/')
@app.route('/index.html')
def serve_index():
    return send_from_directory('.', 'index.html')

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
    user_id = event.source.user_id
    
    # 1. เมื่อได้รับคำสั่งสร้างบิลจาก LIFF
    if "[คำสั่งออมเงิน]" in text:
        try:
            lines = text.split('\n')
            goal_name = lines[1].split(': ')[1]
            total = float(lines[2].split(': ')[1])
            per_person = round((total / 2) / 36, 2)

            # บันทึกลง Supabase
            data = {
                "bill_name": goal_name,
                "total_amount": total,
                "per_person": per_person,
                "status": "pending",
                "created_by": user_id
            }
            res = supabase.table("bills").insert(data).execute()
            bill_id = res.data[0]['id']

            # ส่ง Flex Message บิลสวยๆ
            flex_contents = {
              "type": "bubble",
              "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                  {"type": "text", "text": "🎯 บิลออมเงินใหม่!", "weight": "bold", "color": "#1DB446", "size": "sm"},
                  {"type": "text", "text": goal_name, "weight": "bold", "size": "xl", "margin": "md"},
                  {"type": "separator", "margin": "xxl"},
                  {"type": "box", "layout": "vertical", "margin": "xxl", "spacing": "sm", "contents": [
                      {"type": "box", "layout": "horizontal", "contents": [
                          {"type": "text", "text": "ยอดทั้งหมด", "size": "sm", "color": "#555555", "flex": 0},
                          {"type": "text", "text": f"{total:,.2f} ฿", "size": "sm", "color": "#111111", "align": "end"}
                      ]},
                      {"type": "box", "layout": "horizontal", "contents": [
                          {"type": "text", "text": "เก็บต่อคน", "size": "sm", "color": "#555555", "flex": 0},
                          {"type": "text", "text": f"{per_person:,.2f} ฿", "size": "sm", "color": "#111111", "align": "end", "weight": "bold"}
                      ]}
                  ]}
                ]
              },
              "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                  {
                    "type": "button", "style": "primary", "color": "#1DB446",
                    "action": {
                      "type": "uri", "label": "💰 จ่ายเงิน/ดูรายละเอียด",
                      "uri": f"https://liff.line.me/2009693749-SfmWsP0l?bill_id={bill_id}"
                    }
                  }
                ]
              }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="บิลออมเงินมาแล้วเมี๊ยว!", contents=flex_contents))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาด: {str(e)}"))

    elif text == "สร้างบิล":
        liff_url = "https://liff.line.me/2009693749-SfmWsP0l"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"จิ้มเพื่อตั้งค่าบิลเลยเมี๊ยว! 🐾\n{liff_url}"))

if __name__ == "__main__":
    app.run(port=5000)