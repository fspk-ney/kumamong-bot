import os
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

load_dotenv()
app = Flask(__name__)

line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# Config Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

# --- 🚀 ระบบทวงเงินอัจฉริยะ (เรียกโดย Cron-job ทุก 30 นาที) ---
@app.route('/check_bills')
def check_bills():
    now = datetime.now()
    today = now.date().isoformat()
    
    # ดึงบิลของวันนี้มาตรวจ
    res = supabase.table("bills").select("*").eq("next_due", today).execute()
    
    for bill in res.data:
        try:
            # แปลงเวลาที่ตั้งไว้ (เช่น "08:30") เป็น object
            remind_str = bill.get('remind_time', '08:00')
            remind_time = datetime.strptime(remind_str, "%H:%M").time()
            target_dt = datetime.combine(now.date(), remind_time)
            
            # 🔥 ถ้าตอนนี้เลยเวลาทวงมาแล้ว และไม่เกิน 30 นาที ให้ส่งข้อความ
            if target_dt <= now < (target_dt + timedelta(minutes=30)):
                msg = f"🔔 ฮัลโหลเฮีย! ถึงเวลาออมเงินแล้วเมี๊ยว!\n🎯 รายการ: {bill['bill_name']}\n💰 ยอดที่ต้องออม: {bill['per_person']:,.2f} บาท"
                line_bot_api.push_message(bill['created_by'], TextSendMessage(text=msg))
                
                # เลื่อนวันนัดงวดถัดไป
                current_due = datetime.strptime(bill['next_due'], '%Y-%m-%d')
                unit = bill.get('freq_unit', '7d')
                
                if 'd' in unit:
                    next_due = current_due + timedelta(days=int(unit.replace('d', '')))
                elif 'm' in unit:
                    next_due = current_due + relativedelta(months=int(unit.replace('m', '')))
                
                # อัปเดตวันที่ใหม่ลงฐานข้อมูล
                supabase.table("bills").update({"next_due": next_due.date().isoformat()}).eq("id", bill['id']).execute()
        except Exception as e:
            print(f"Error: {e}")
            
    return "Checked", 200

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
        # (ส่งเมนูเหมือนเดิมครับเฮีย)
        flex_menu = {
            "type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "🐾 คุ้มมงมาแล้ว!", "weight": "bold", "size": "lg"},
                {"type": "button", "style": "primary", "color": "#1DB446", "margin": "md", "action": {"type": "uri", "label": "💰 ออมเงินใหม่", "uri": f"https://liff.line.me/{MY_LIFF_ID}"}}
            ]}
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="คุ้มมงมาแล้ว!", contents=flex_menu))

    elif "[คำสั่งออมเงิน]" in text:
        try:
            lines = text.split('\n')
            goal = lines[1].split(': ')[1]
            total = float(lines[2].split(': ')[1])
            count = int(lines[3].split(': ')[1])
            unit = lines[4].split(': ')[1]
            start = lines[5].split(': ')[1]
            time = lines[6].split(': ')[1] # รับเวลาทวง

            per_person = round((total / 2) / count, 2)
            data = {
                "bill_name": goal, "total_amount": total, "per_person": per_person,
                "status": "pending", "created_by": user_id,
                "freq_unit": unit, "next_due": start, "remind_time": time
            }
            supabase.table("bills").insert(data).execute()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ บันทึกบิล '{goal}' แล้ว! คุ้มมงจะทวงทุกวันที่ถึงกำหนดตอน {time} นะเมี๊ยว!"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พลาด: {str(e)}"))

if __name__ == "__main__":
    app.run(port=5000)