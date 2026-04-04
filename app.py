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

# 1. LINE Config
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 2. Supabase Config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

try:
    # ตรวจสอบว่ามีค่าครบไหมก่อนเชื่อมต่อ
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("URL หรือ Key ของ Supabase ว่างเปล่า!")
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
    
    # --- คำสั่งพื้นฐาน ---
    if text == "เมี๊ยว":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="เรียกทำไมมนุษย์! คุ้มมงมาแล้วเมี๊ยว! 🐾"))
        return

    # --- คำสั่งเรียกเปิดหน้าสร้างบิล (เฮียต้องมีอันนี้!) ---
    if text == "สร้างบิล":
        # เปลี่ยน ID ตรงนี้ให้เป็นของเฮียนะเมี๊ยว!
        liff_url = "https://liff.line.me/2009693749-SfmWsP0l" 
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"จิ้มเพื่อตั้งค่าบิลเลยเมี๊ยว! 🐾\n{liff_url}"))
        return

    # --- เมื่อได้รับข้อมูลจาก LIFF เพื่อสร้างบิลลง Database ---
    if "[คำสั่งออมเงิน]" in text:
        if supabase is None:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ระบบฐานข้อมูลมีปัญหา (เช็ค URL/Key ใน Render นะเมี๊ยว)"))
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

            # ส่ง Flex Message บิลสวยๆ
            flex_contents = {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "🎯 บิลออมเงินใหม่!", "weight": "bold", "color": "#1DB446", "size": "sm"},
                        {"type": "text", "text": goal_name, "weight": "bold", "size": "xl", "margin": "md"},
                        {"type": "separator", "margin": "lg"},
                        {"type": "box", "layout": "vertical", "margin": "lg", "contents": [
                            {"type": "text", "text": f"ยอดรวม: {total:,.2f} บาท", "size": "sm"},
                            {"type": "text", "text": f"เก็บคนละ: {per_person:,.2f} บาท/งวด", "weight": "bold", "size": "md", "color": "#111111"}
                        ]}
                    ]
                },
                "footer": {
                    "type": "box", "layout": "vertical",
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
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="บิลมาแล้วเมี๊ยว!", contents=flex_contents))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"บอสครับ บั๊กโผล่ตอนบันทึก: {str(e)}"))

    # --- เมื่อได้รับคำสั่งยืนยันการจ่ายเงิน ---
    elif "[ยืนยันจ่ายเงิน]" in text:
        try:
            bill_id = text.split('\n')[1].split(': ')[1]
            supabase.table("bills").update({"status": "paid"}).eq("id", bill_id).execute()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚡️ เรียบร้อย! คุ้มมงบันทึกให้แล้วว่าเฮียจ่ายแล้วเมี๊ยว! 🐾"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"จ่ายเงินพลาด: {str(e)}"))

if __name__ == "__main__":
    app.run(port=5000)