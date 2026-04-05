import os
import pytz
from flask import Flask, request, abort, send_from_directory
from flask_cors import CORS  # <--- นำเข้า CORS
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, PostbackEvent
from supabase import create_client, Client
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
CORS(app)  # <--- เปิดใช้งาน CORS ทันทีหลังจากสร้าง app

# --- ข้อมูล Config ของเฮีย ---
LINE_ACCESS_TOKEN = "UXPznDfBmyuDMV/OX32Y6htg/EGdPjNEVoLvngkysgodSaLgUstA6ewbNcg7A0vJw5P4EUXHgRMhkxRBvpUYgB6Fp/ZgMpyRLtcL/4joySV5u5JSvOpQmq2qrHN+I1wZ/I7pw5zr9IolfsRyWoz+sQdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "a06d44bf8e6d6079c04d3ba052078e25"
SUPABASE_URL = "https://jvuhjuvvarpjcwpgwkny.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp2dWhqdXZ2YXJwamN3cGd3a255Iiwicm9sZSI6Imp2dWhqdXZ2YXJwamN3cGd3a255Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTMwNTQzMiwiZXhwIjoyMDkwODgxNDMyfQ.AhRvojeTCD9HmC5-jUXDzT_6wojUoe7rJ9kQoXpkslk"
MY_LIFF_ID = "2009693749-SfmWsP0l"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/list')
def serve_list():
    return send_from_directory('.', 'list.html')

# --- 🚀 [ใหม่] รับข้อมูลจากหน้าเว็บโดยตรง ---
@app.route("/create_saving_api", methods=['POST'])
def create_saving_api():
    data = request.get_json()
    try:
        goal = data['goal']
        total_project_amount = float(data['total'])
        total_installments = int(data['count'])
        unit = data['unit']
        start_str = data['start']
        time_str = data['time']
        t_ids = data['targetIds'].split(',')
        t_names = data['targetNames'].split(',')
        group_id = data.get('groupId', 'personal')
        user_id = data.get('userId')

        num_people = len(t_ids)
        amount_per_person_total = total_project_amount / num_people
        amount_per_person_per_period = round(amount_per_person_total / total_installments, 2)
        
        base_time = datetime.strptime(f"{start_str} {time_str}", "%Y-%m-%d %H:%M")

        # บันทึกลง Supabase ทีละงวด
# บันทึกลง Supabase ทีละงวด
        for i in range(total_installments):
            if unit == "1d": due_time = base_time + timedelta(days=i)
            elif unit == "7d": due_time = base_time + timedelta(weeks=i)
            elif unit == "14d": due_time = base_time + timedelta(weeks=i*2)
            elif unit == "1m": due_time = base_time + relativedelta(months=i)
            else: due_time = base_time + timedelta(days=i)

            due_str = due_time.strftime('%Y-%m-%d %H:%M:%S')

            for tid, tname in zip(t_ids, t_names):
                supabase.table("bills").insert({
                    "bill_name": goal, "total_amount": total_project_amount, "per_person": amount_per_person_per_period,
                    "status": "pending", "created_by": user_id, "freq_unit": unit, "next_due": due_str,
                    "remind_time": time_str, "target_user_id": tid, "member_name": tname, "group_id": group_id
                }).execute()

        # ✅ ย้ายออกมาข้างนอก Loop (ไม่งั้นบอทจะส่งข้อความรัวตามจำนวนงวด)
        target = group_id if group_id != 'personal' else user_id
        confirm_text = f"🪙 บันทึกรายการสำเร็จ!\n📌 รายการ: {goal}\n💰 ยอดรวม: {total_project_amount:,.2f} บาท\n👥 สมาชิก: {data['targetNames']}\n\nมะมงรับทราบ! เดี๋ยวทวงให้ตามเวลาครับ"
        line_bot_api.push_message(target, TextSendMessage(text=confirm_text))

        return "OK", 200
    except Exception as e:
        print(f"Error in API: {e}") # ช่วย debug ดูที่ log ของ Render
        return str(e), 500

# --- 🚀 ระบบทวงเงิน ---
@app.route('/check_bills')
def check_bills():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    
    res = supabase.table("bills").select("*").lte("next_due", now_str).neq("status", "paid").execute()
    if not res.data: return "No bills due", 200
    
    grouped_installments = {}
    for bill in res.data:
        installment_key = f"{bill['bill_name']}_{bill.get('group_id')}_{bill['next_due']}"
        if installment_key not in grouped_installments:
            grouped_installments[installment_key] = []
        grouped_installments[installment_key].append(bill)

    for key, members in grouped_installments.items():
        try:
            sample = members[0]
            bill_name = sample['bill_name']
            due_time = sample['next_due']
            target_destination = sample.get('group_id') or sample.get('target_user_id') or sample['created_by']
            
            all_res = supabase.table("bills").select("next_due").eq("bill_name", bill_name).order("next_due").execute()
            unique_dates = sorted(list(set([b['next_due'] for b in all_res.data])))
            total_inst = len(unique_dates)
            current_inst = unique_dates.index(due_time) + 1

            member_list_ui = []
            for m in members:
                member_list_ui.append({
                    "type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": f" {m['member_name']}", "size": "sm", "color": "#77614F", "flex": 4},
                        {"type": "text", "text": "ยังไม่จ่าย", "size": "xs", "color": "#E65C4E", "align": "end", "flex": 2}
                    ]
                })

            flex = {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": f"📢 งวดที่ {current_inst}/{total_inst} มาแล้วครับ!", "weight": "bold", "color": "#ADC993", "size": "sm"},
                        {"type": "text", "text": bill_name, "weight": "bold", "size": "xl", "margin": "md"},
                        {"type": "text", "text": f"กำหนดจ่าย: {due_time}", "size": "xs", "color": "#77614F", "weight": "bold"},
                        {"type": "text", "text": f"ยอดต่อคน: {sample['per_person']:,.2f} บาท", "size": "xs", "color": "#77614F", "margin": "xs"},
                        {"type": "separator", "margin": "lg"},
                        {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "xs", "contents": member_list_ui},
                        {"type": "separator", "margin": "lg"},
                        {"type": "text", "text": "* อัปเดตสถานะล่าสุด โฮ่ง", "size": "xs", "color": "#aaaaaa", "margin": "md"}
                    ]
                },
                "footer": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "button", "style": "primary", "color": "#ADC993", "action": {
                            "type": "uri", "label": "แจ้งจ่ายเงิน / ดูทั้งหมด", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"
                        }}
                    ]
                }
            }
            line_bot_api.push_message(target_destination, FlexSendMessage(alt_text=f"งวดที่ {current_inst} บิล {bill_name}", contents=flex))
        except Exception as e: print(f"Error in check_bills: {e}")
            
    return "Check Complete", 200

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
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มะมงบันทึกว่าคุณจ่าย '{bill_name}' เรียบร้อยแล้วครับ! "))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    source = event.source
    group_id = 'personal'
    if hasattr(source, 'group_id'): group_id = source.group_id
    elif hasattr(source, 'room_id'): group_id = source.room_id

    if text == "มะมง":
        reply_text = "สวัสดีครับ มะมงมาแล้วครับผม 🐶 จะให้มะหมาตัวนี้ช่วยเรื่องอะไรดีครับ"
        flex_menu = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "มะมงยินดีบริการ โฮ่ง โฮ่ง!🐾", "weight": "bold", "size": "lg", "align": "center"},
                    {"type": "text", "text": reply_text, "size": "sm", "wrap": True, "margin": "sm", "color": "#666666"},
                    {"type": "button", "style": "primary", "color": "#ADC993", "margin": "md", "action": {"type": "uri", "label": "🪙 สร้างรายการออม", "uri": f"https://liff.line.me/{MY_LIFF_ID}?groupId={group_id}"}},
                    {"type": "button", "style": "secondary", "color": "#F5EFE4", "margin": "md", "action": {"type": "uri", "label": "📄 เช็ครายการออม", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"}}
                ]
            }
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="มะมงมาแล้วครับ!", contents=flex_menu))

if __name__ == "__main__":
    app.run(port=5000)