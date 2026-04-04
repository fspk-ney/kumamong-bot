import os
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, PostbackEvent
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

MY_LIFF_ID = "2009693749-SfmWsP0l" 

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

# --- 🚀 ระบบทวงเงินอัจฉริยะ (เรียกโดย Cron-job ทุก 30 นาที) ---
@app.route('/check_bills')
def check_bills():
    now = datetime.now()
    today = now.date().isoformat()
    
    res = supabase.table("bills").select("*").eq("next_due", today).execute()
    
    for bill in res.data:
        try:
            remind_str = bill.get('remind_time', '08:00')
            remind_time = datetime.strptime(remind_str, "%H:%M").time()
            target_dt = datetime.combine(now.date(), remind_time)
            
            # ถ้าถึงเวลาทวง (ภายในหน้าต่าง 30 นาที)
            if target_dt <= now < (target_dt + timedelta(minutes=30)):
                # ส่ง Flex Message พร้อมปุ่มยืนยันการจ่าย
                flex_reminder = {
                    "type": "bubble",
                    "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "🔔 ถึงเวลาออมเงิน!", "weight": "bold", "color": "#1DB446"}]},
                    "body": {"type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": f"🎯 รายการ: {bill['bill_name']}", "size": "sm", "weight": "bold"},
                        {"type": "text", "text": f"💰 ยอด: {bill['per_person']:,.2f} บาท", "size": "xl", "margin": "md", "color": "#111111"}
                    ]},
                    "footer": {"type": "box", "layout": "vertical", "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446", "action": {
                            "type": "postback", "label": "✅ จ่ายแล้วเมี๊ยว", "data": f"action=pay&bill_id={bill['id']}&name={bill['bill_name']}"
                        }}
                    ]}
                }
                line_bot_api.push_message(bill['created_by'], FlexSendMessage(alt_text="ทวงเงินออมเมี๊ยว!", contents=flex_reminder))
                
                # คำนวณงวดถัดไป และรีเซ็ต Status เป็น pending สำหรับงวดหน้า
                current_due = datetime.strptime(bill['next_due'], '%Y-%m-%d')
                unit = bill.get('freq_unit', '7d')
                if 'd' in unit:
                    next_due = current_due + timedelta(days=int(unit.replace('d', '')))
                elif 'm' in unit:
                    next_due = current_due + relativedelta(months=int(unit.replace('m', '')))
                
                # อัปเดตวันที่ และคืนค่าสถานะเป็น pending
                supabase.table("bills").update({
                    "next_due": next_due.date().isoformat(),
                    "status": "pending" 
                }).eq("id", bill['id']).execute()
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

# --- 🎯 จัดการการกดปุ่ม (จ่ายแล้ว) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    if "action=pay" in data:
        params = dict(x.split('=') for x in data.split('&'))
        bill_id = params['bill_id']
        bill_name = params.get('name', 'รายการออม')
        
        # อัปเดตสถานะเป็น paid ใน Supabase
        supabase.table("bills").update({"status": "paid"}).eq("id", bill_id).execute()
        
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=f"🎉 รับทราบเมี๊ยว! บันทึกว่าเฮียจ่ายรายการ '{bill_name}' เรียบร้อยแล้ว! เก่งมากเมี๊ยว! 🐾")
        )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id

    if text == "เมี๊ยว":
        flex_menu = {
            "type": "bubble",
            "hero": {"type": "image", "url": "https://img5.pic.in.th/file/secure-sv1/kumamong_header.png", "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "🐾 คุ้มมงยินดีบริการเมี๊ยว!", "weight": "bold", "size": "lg", "align": "center"},
                {"type": "button", "style": "primary", "color": "#1DB446", "margin": "md", "action": {"type": "uri", "label": "💰 ออมเงินใหม่", "uri": f"https://liff.line.me/{MY_LIFF_ID}"}},
                {"type": "button", "style": "secondary", "margin": "md", "action": {"type": "message", "label": "📊 ดูรายการออม", "text": "ดูรายการออม"}}
            ]}
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="คุ้มมงมาแล้ว!", contents=flex_menu))

    elif text == "ดูรายการออม":
        # ดึงข้อมูลบิลทั้งหมดของผู้ใช้
        res = supabase.table("bills").select("*").eq("created_by", user_id).execute()
        if not res.data:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ยังไม่มีรายการออมเลยเมี๊ยว! เริ่มออมกันเถอะ!"))
            return

        msg = "📋 รายการออมของเฮีย:\n"
        for bill in res.data:
            status_icon = "✅" if bill['status'] == "paid" else "❌"
            msg += f"\n{status_icon} {bill['bill_name']}\n💰 คนละ: {bill['per_person']:,.2f} บาท\n📅 นัดหน้า: {bill['next_due']}\n---"
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif "[คำสั่งออมเงิน]" in text:
        try:
            lines = text.split('\n')
            goal = lines[1].split(': ')[1]
            total = float(lines[2].split(': ')[1])
            count = int(lines[3].split(': ')[1])
            unit = lines[4].split(': ')[1]
            start = lines[5].split(': ')[1]
            time = lines[6].split(': ')[1]

            per_person = round((total / 2) / count, 2)
            data = {
                "bill_name": goal, "total_amount": total, "per_person": per_person,
                "status": "pending", "created_by": user_id,
                "freq_unit": unit, "next_due": start, "remind_time": time
            }
            supabase.table("bills").insert(data).execute()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ บันทึกบิล '{goal}' แล้ว!\n💰 ออมงวดละ: {per_person:,.2f} บาท\n⏰ ทวงตอน: {time}\nคุ้มมงจะคอยสะกิดนะเมี๊ยว!"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พลาด: {str(e)}"))

if __name__ == "__main__":
    app.run(port=5000)