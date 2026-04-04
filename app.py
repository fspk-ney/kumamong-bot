import os
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, PostbackEvent
from supabase import create_client, Client
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# --- ข้อมูล Config ของเฮีย ---
LINE_ACCESS_TOKEN = "UXPznDfBmyuDMV/OX32Y6htg/EGdPjNEVoLvngkysgodSaLgUstA6ewbNcg7A0vJw5P4EUXHgRMhkxRBvpUYgB6Fp/ZgMpyRLtcL/4joySV5u5JSvOpQmq2qrHN+I1wZ/I7pw5zr9IolfsRyWoz+sQdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "a06d44bf8e6d6079c04d3ba052078e25"
SUPABASE_URL = "https://jvuhjuvvarpjcwpgwkny.supabase.co"
SUPABASE_KEY = "sb_publishable_H3wOadSnVy-bEwHt0Ls5kA_8V8Olboe"
MY_LIFF_ID = "2009693749-SfmWsP0l" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def serve_index(): return send_from_directory('.', 'index.html')

@app.route('/list')
def serve_list(): return send_from_directory('.', 'list.html')

# --- 🚀 ระบบทวงเงินอัตโนมัติ (เช็กทุก 30 นาที) ---
@app.route('/check_bills')
def check_bills():
    now = datetime.now()
    today = now.date().isoformat()
    # ดึงบิลที่ถึงกำหนดวันนี้
    res = supabase.table("bills").select("*").eq("next_due", today).execute()
    
    for bill in res.data:
        try:
            remind_str = bill.get('remind_time', '08:00')
            remind_time = datetime.strptime(remind_str, "%H:%M").time()
            target_dt = datetime.combine(now.date(), remind_time)
            
            # ถ้าถึงเวลาทวง (ช่วง 30 นาที)
            if target_dt <= now < (target_dt + timedelta(minutes=30)):
                receiver_id = bill.get('target_user_id') or bill['created_by']
                
                flex = {
                    "type": "bubble",
                    "header": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "🔔 คุ้มมงมาทวงเงินแล้วเมี๊ยว!", "weight": "bold", "color": "#1DB446"}]},
                    "body": {"type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": f"🎯 รายการ: {bill['bill_name']}", "weight": "bold", "size": "md"},
                        {"type": "text", "text": f"💰 ยอดที่ต้องออม: {bill['per_person']:,.2f} บาท", "size": "xl", "margin": "md", "color": "#111111"},
                        {"type": "text", "text": f"👤 สมาชิก: {bill['member_name']}", "size": "sm", "color": "#888888", "margin": "sm"}
                    ]},
                    "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446", "action": {
                            "type": "postback", "label": "✅ จ่ายเรียบร้อยแล้ว", "data": f"action=pay&bill_id={bill['id']}&name={bill['bill_name']}"
                        }},
                        {"type": "button", "style": "link", "height": "sm", "action": {
                            "type": "uri", "label": "📊 ดูรายการทั้งหมด", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"
                        }}
                    ]}
                }
                line_bot_api.push_message(receiver_id, FlexSendMessage(alt_text="ได้เวลาออมเงิน!", contents=flex))
                
                # คำนวณงวดถัดไป
                unit = bill.get('freq_unit', '7d')
                curr_due = datetime.strptime(bill['next_due'], '%Y-%m-%d')
                if 'd' in unit:
                    nxt = curr_due + timedelta(days=int(unit.replace('d', '')))
                else:
                    nxt = curr_due + relativedelta(months=int(unit.replace('m', '')))
                
                # อัปเดตงวดถัดไป และรีเซ็ตสถานะเป็น pending
                supabase.table("bills").update({"next_due": nxt.date().isoformat(), "status": "pending"}).eq("id", bill['id']).execute()
        except Exception as e:
            print(f"Error: {e}")
            
    return "OK", 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    return 'OK'

@handler.add(PostbackEvent)
def handle_postback(event):
    data_str = event.postback.data
    params = dict(x.split('=') for x in data_str.split('&'))
    if params.get('action') == 'pay':
        bill_id = params['bill_id']
        bill_name = params.get('name', 'รายการออม')
        supabase.table("bills").update({"status": "paid"}).eq("id", bill_id).execute()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 เก่งมากเมี๊ยว! บันทึกว่าจ่าย '{bill_name}' เรียบร้อยแล้ว! 🐾"))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id
    group_id = getattr(event.source, 'group_id', 'personal')

    # --- 🤫 ระบบจำชื่อเพื่อน (ห้ามลบ!) ---
    try:
        profile = line_bot_api.get_profile(user_id)
        supabase.table("group_members").upsert({
            "group_id": group_id, "user_id": user_id, "display_name": profile.display_name
        }).execute()
    except: pass

    if text == "เมี๊ยว":
        flex_menu = {
            "type": "bubble",
            "hero": {"type": "image", "url": "https://img5.pic.in.th/file/secure-sv1/kumamong_header.png", "size": "full", "aspectRatio": "20:13", "aspectMode": "cover"},
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "🐾 คุ้มมงยินดีบริการเมี๊ยว!", "weight": "bold", "size": "lg", "align": "center"},
                {"type": "button", "style": "primary", "color": "#1DB446", "margin": "md", "action": {"type": "uri", "label": "💰 สร้างรายการออมใหม่", "uri": f"https://liff.line.me/{MY_LIFF_ID}?groupId={group_id}"}},
                {"type": "button", "style": "secondary", "margin": "md", "action": {"type": "uri", "label": "📊 ดูสถานะคนจ่าย", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"}}
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
            t_id = lines[7].split(': ')[1]
            t_name = lines[8].split(': ')[1]

            per_person = round(total / count, 2) # คำนวณยอดต่อคนต่อรอบ
            
            data = {
                "bill_name": goal, "total_amount": total, "per_person": per_person,
                "status": "pending", "created_by": user_id, "freq_unit": unit,
                "next_due": start, "remind_time": time, "target_user_id": t_id, "member_name": t_name
            }
            supabase.table("bills").insert(data).execute()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ บันทึกบิล '{goal}' ของ {t_name} เรียบร้อย! เดี๋ยวคุ้มมงจัดการทวงให้เองเมี๊ยว!"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาด: {str(e)}"))

if __name__ == "__main__": app.run(port=5000)