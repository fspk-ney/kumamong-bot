import os
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# LINE Config
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# Supabase Config (ใส่ตัวแปรดักไว้เผื่อ Error)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase Connection Error: {e}")
    supabase = None

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
    
    # คำสั่ง เมี๊ยว (แยกออกมาไว้บนสุดให้เช็กง่ายๆ)
    if text == "เมี๊ยว":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="เรียกทำไมมนุษย์! คุ้มมงมาแล้วเมี๊ยว! 🐾"))
        return

    if "[คำสั่งออมเงิน]" in text:
        if supabase is None:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ระบบฐานข้อมูลมีปัญหา ติดต่อแอดมินนะเมี๊ยว!"))
            return
        
        try:
            lines = text.split('\n')
            goal_name = lines[1].split(': ')[1]
            total = float(lines[2].split(': ')[1])
            per_person = round((total / 2) / 36, 2)

            data = {
                "bill_name": goal_name,
                "total_amount": total,
                "per_person": per_person,
                "status": "pending",
                "created_by": event.source.user_id
            }
            res = supabase.table("bills").insert(data).execute()
            bill_id = res.data[0]['id']

            # ส่ง Flex Message
            flex_contents = {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎯 บิลออมเงินใหม่!", "weight": "bold", "color": "#1DB446"},
                        {"type": "text", "text": goal_name, "weight": "bold", "size": "xl", "margin": "md"}
                    ]
                },
                "footer": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446",
                         "action": {"type": "uri", "label": "💰 ดูรายละเอียด", "uri": f"https://liff.line.me/2009693749-SfmWsP0l?bill_id={bill_id}"}}
                    ]
                }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="บิลมาแล้ว!", contents=flex_contents))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"บอสครับ บั๊กโผล่: {str(e)}"))

if __name__ == "__main__":
    app.run(port=5000)