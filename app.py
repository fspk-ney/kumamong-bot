import os
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Config LINE
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# Config Supabase (ดึงจาก Render Environment)
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
    user_id = event.source.user_id
    MY_LIFF_ID = "2009693749-SfmWsP0l" 

    if text == "เมี๊ยว":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="เรียกทำไมมนุษย์! คุ้มมงมาแล้วเมี๊ยว! 🐾"))
    
    elif text == "สร้างบิล":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"จิ้มเพื่อตั้งค่าบิลเลยเมี๊ยว! 🐾\nhttps://liff.line.me/{MY_LIFF_ID}"))

    elif text == "ประวัติ":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เช็กประวัติการออมทั้งหมดของเฮียได้ที่นี่เมี๊ยว! 📊\nhttps://liff.line.me/{MY_LIFF_ID}"))

    elif "[คำสั่งออมเงิน]" in text:
        try:
            lines = text.split('\n')
            goal_name = lines[1].split(': ')[1]
            total = float(lines[2].split(': ')[1])
            per_person = round((total / 2) / 36, 2)

            data = {"bill_name": goal_name, "total_amount": total, "per_person": per_person, "status": "pending", "created_by": user_id}
            res = supabase.table("bills").insert(data).execute()
            bill_id = res.data[0]['id']

            flex_contents = {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎯 บิลออมเงินใหม่!", "weight": "bold", "color": "#1DB446"},
                        {"type": "text", "text": goal_name, "weight": "bold", "size": "xl", "margin": "md"},
                        {"type": "separator", "margin": "lg"},
                        {"type": "text", "text": f"เก็บคนละ: {per_person:,.2f} บาท", "margin": "md", "weight": "bold"}
                    ]
                },
                "footer": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446",
                         "action": {"type": "uri", "label": "💰 จ่ายเงิน/ดูรายละเอียด", "uri": f"https://liff.line.me/{MY_LIFF_ID}?bill_id={bill_id}"}}
                    ]
                }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="บิลมาแล้ว!", contents=flex_contents))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"บันทึกพลาด: {str(e)}"))

    elif "[ยืนยันจ่ายเงิน]" in text:
        try:
            bill_id = text.split('\n')[1].split(': ')[1]
            supabase.table("bills").update({"status": "paid"}).eq("id", bill_id).execute()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚡️ เรียบร้อย! คุ้มมงบันทึกให้แล้วว่าเฮียจ่ายแล้วเมี๊ยว! 🐾"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"จ่ายเงินพลาด: {str(e)}"))

if __name__ == "__main__":
    app.run(port=5000)