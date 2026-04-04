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

@app.route('/list')
def serve_list():
    return send_from_directory('.', 'list.html')

# --- 🚀 ระบบทวงเงิน (ทวงไปหา target_user_id) ---
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
            
            if target_dt <= now < (target_dt + timedelta(minutes=30)):
                # ส่งหา target_user_id (คนที่จะโดนทวง)
                receiver_id = bill.get('target_user_id') or bill['created_by']
                
                flex_reminder = {
                    "type": "bubble",
                    "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "🔔 ถึงเวลาออมเงินเมี๊ยว!", "weight": "bold", "color": "#1DB446"}]},
                    "body": {"type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": f"🎯 รายการ: {bill['bill_name']}", "size": "md", "weight": "bold"},
                        {"type": "text", "text": f"💰 ยอด: {bill['per_person']:,.2f} บาท", "size": "xl", "margin": "md", "color": "#111111"},
                        {"type": "text", "text": f"👤 ของ: {bill['member_name']}", "size": "sm", "color": "#888888"}
                    ]},
                    "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446", "action": {
                            "type": "postback", "label": "✅ ชำระเงินแล้วเมี๊ยว", "data": f"action=pay&bill_id={bill['id']}&name={bill['bill_name']}"
                        }},
                        {"type": "button", "style": "link", "height": "sm", "action": {
                            "type": "uri", "label": "📋 ดูรายการทั้งหมด", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"
                        }}
                    ]}
                }
                line_bot_api.push_message(receiver_id, FlexSendMessage(alt_text="ทวงเงินออม!", contents=flex_reminder))
                
                # อัปเดตงวดถัดไป
                current_due = datetime.strptime(bill['next_due'], '%Y-%m-%d')
                unit = bill.get('freq_unit', '7d')
                if 'd' in unit:
                    next_due = current_due + timedelta(days=int(unit.replace('d', '')))
                elif 'm' in unit:
                    next_due = current_due + relativedelta(months=int(unit.replace('m', '')))
                
                supabase.table("bills").update({"next_due": next_due.date().isoformat(), "status": "pending"}).eq("id", bill['id']).execute()
        except Exception as e:
            print(f"Error in check_bills: {e}")
            
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

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    if "action=pay" in data:
        params = dict(x.split('=') for x in data.split('&'))
        bill_id = params['bill_id']
        bill_name = params.get('name', 'รายการออม')
        supabase.table("bills").update({"status": "paid"}).eq("id", bill_id).execute()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 รับทราบเมี๊ยว! บันทึกว่าเฮียจ่าย '{bill_name}' เรียบร้อย!"))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id
    group_id = getattr(event.source, 'group_id', 'personal') # ดึง ID กลุ่ม

    # --- 🤫 ระบบจำสมาชิก (ใครพิมพ์มา จำชื่อหมด!) ---
    try:
        profile = line_bot_api.get_profile(user_id)
        supabase.table("group_members").upsert({
            "group_id": group_id,
            "user_id": user_id,
            "display_name": profile.display_name
        }).execute()
    except: pass

    if text == "เมี๊ยว":
        flex_menu = {
            "type": "bubble",
            "hero": {"type": "image", "url": "https://img5.pic.in.th/file/secure-sv1/kumamong_header.png", "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "🐾 คุ้มมงยินดีบริการเมี๊ยว!", "weight": "bold", "size": "lg", "align": "center"},
                {"type": "button", "style": "primary", "color": "#1DB446", "margin": "md", "action": {"type": "uri", "label": "💰 ออมเงินใหม่", "uri": f"https://liff.line.me/{MY_LIFF_ID}?groupId={group_id}"}},
                {"type": "button", "style": "secondary", "margin": "md", "action": {"type": "uri", "label": "📊 เช็กสถานะ จ่าย/ไม่จ่าย", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"}}
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
            time = lines[6].split(': ')[1]
            target_id = lines[7].split(': ')[1] # ID คนที่จะโดนทวง
            target_name = lines[8].split(': ')[1] # ชื่อคนที่จะโดนทวง

            per_person = round((total / 2) / count, 2)
            data = {
                "bill_name": goal, "total_amount": total, "per_person": per_person,
                "status": "pending", "created_by": user_id,
                "freq_unit": unit, "next_due": start, "remind_time": time,
                "target_user_id": target_id, "member_name": target_name
            }
            supabase.table("bills").insert(data).execute()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ บันทึกบิล '{goal}' ของ {target_name} เรียบร้อย! เดี๋ยวคุ้มมงจัดการทวงให้เมี๊ยว!"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"พลาด: {str(e)}"))

if __name__ == "__main__":
    app.run(port=5000)