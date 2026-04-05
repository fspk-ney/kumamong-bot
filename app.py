import os
import pytz
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, PostbackEvent
from supabase import create_client, Client
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# --- Config ---
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

# --- 🚀 ฟังก์ชันหลัก: เช็คและพ่นบิล (ดึงออกมาเป็นฟังก์ชันแยกเพื่อให้เรียกซ้ำได้) ---
def trigger_bill_notification(target_group_id=None):
    res = supabase.table("bills").select("*").execute()
    if not res.data: return
    
    grouped_bills = {}
    for bill in res.data:
        key = f"{bill['bill_name']}_{bill.get('group_id', 'personal')}"
        if key not in grouped_bills: grouped_bills[key] = []
        grouped_bills[key].append(bill)

    for key, members in grouped_bills.items():
        try:
            # ถ้าส่ง target_group_id มา ให้ส่งเฉพาะกลุ่มนั้น (กันบิลกลุ่มอื่นเด้งรบกวน)
            current_group = members[0].get('group_id') or 'personal'
            if target_group_id and current_group != target_group_id: continue

            bill_name = members[0]['bill_name']
            target = members[0].get('group_id') or members[0].get('target_user_id') or members[0]['created_by']
            
            if all(m['status'] == 'paid' for m in members): continue 

            member_list_ui = []
            for m in members:
                is_paid = m['status'] == 'paid'
                color = "#1DB446" if is_paid else "#ff4d4d"
                member_list_ui.append({
                    "type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": f"{'✅' if is_paid else '⏳'} {m['member_name']}", "size": "sm", "flex": 4},
                        {"type": "text", "text": "จ่ายแล้ว" if is_paid else "ยังไม่จ่าย", "size": "xs", "color": color, "align": "end", "flex": 2}
                    ]
                })

            flex = {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": "💰 รายละเอียดบิลกลุ่มโดยมะมง 🐶", "weight": "bold", "color": "#1DB446", "size": "sm"},
                        {"type": "text", "text": bill_name, "weight": "bold", "size": "xl", "margin": "md"},
                        {"type": "text", "text": f"ยอดต่อคน: {members[0]['per_person']:,.2f} บาท", "size": "xs", "color": "#888888"},
                        {"type": "separator", "margin": "lg"},
                        {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "xs", "contents": member_list_ui},
                        {"type": "separator", "margin": "lg"},
                        {"type": "text", "text": "* มะมงอัปเดตให้ล่าสุดครับ 🐾", "size": "xs", "color": "#aaaaaa", "margin": "md"}
                    ]
                },
                "footer": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446", "action": {"type": "uri", "label": "✅ แจ้งจ่ายเงิน / ดูทั้งหมด", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"}}
                    ]
                }
            }
            line_bot_api.push_message(target, FlexSendMessage(alt_text=f"มะมงอัปเดตบิล {bill_name}", contents=flex))
        except Exception as e: print(f"Error: {e}")

@app.route('/check_bills')
def check_bills_route():
    trigger_bill_notification()
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
    params = dict(x.split('=') for x in event.postback.data.split('&'))
    if params.get('action') == 'pay':
        supabase.table("bills").update({"status": "paid"}).eq("id", params['bill_id']).execute()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 มะมงบันทึกว่าจ่ายเรียบร้อยแล้วครับ! 🐾"))
        # หลังจากกดจ่าย ให้พ่นบิลอัปเดตออกมาใหม่ทันที
        group_id = getattr(event.source, 'group_id', getattr(event.source, 'room_id', None))
        trigger_bill_notification(group_id)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text, user_id = event.message.text.strip(), event.source.user_id
    group_id = getattr(event.source, 'group_id', getattr(event.source, 'room_id', 'personal'))

    if text == "มะมง":
        flex_menu = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "contents": [
                    {"type": "text", "text": "🐾 มะมงยินดีบริการครับผม!", "weight": "bold", "size": "lg", "align": "center"},
                    {"type": "text", "text": "สวัสดีครับ มะมงมาแล้วครับผม 🐶 จะให้ช่วยออมเงินเรื่องอะไรดีครับเฮีย?", "size": "sm", "wrap": True, "margin": "sm", "color": "#666666"},
                    {"type": "button", "style": "primary", "color": "#1DB446", "margin": "md", "action": {"type": "uri", "label": "💰 สร้างรายการออมใหม่", "uri": f"https://liff.line.me/{MY_LIFF_ID}?groupId={group_id}"}},
                    {"type": "button", "style": "secondary", "margin": "md", "action": {"type": "uri", "label": "📊 ดูสถานะคนจ่าย", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"}}
                ]
            }
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="มะมงมาแล้วครับ!", contents=flex_menu))

    elif "[คำสั่งออมเงิน]" in text:
        try:
            lines = text.split('\n')
            goal = lines[1].split(': ')[1]
            total_amt = float(lines[2].split(': ')[1])
            installments = int(lines[3].split(': ')[1])
            unit = lines[4].split(': ')[1]
            start_dt = datetime.strptime(f"{lines[5].split(': ')[1]} {lines[6].split(': ')[1]}", "%Y-%m-%d %H:%M")
            t_ids = [i.strip() for i in lines[7].split(': ')[1].split(',')]
            t_names = [n.strip() for n in lines[8].split(': ')[1].split(',')]
            per_period = round((total_amt / len(t_ids)) / installments, 2)

            for i in range(installments):
                if unit == "10_minutes": due = start_dt + timedelta(minutes=i * 10)
                elif unit == "daily": due = start_dt + timedelta(days=i)
                elif unit == "weekly": due = start_dt + timedelta(weeks=i)
                elif unit == "monthly": due = start_dt + relativedelta(months=i)
                else: due = start_dt + timedelta(days=i)

                for tid, tname in zip(t_ids, t_names):
                    supabase.table("bills").insert({
                        "bill_name": goal, "total_amount": total_amt, "per_person": per_period,
                        "status": "pending", "created_by": user_id, "next_due": due.strftime('%Y-%m-%d %H:%M:%S'),
                        "target_user_id": tid, "member_name": tname, "group_id": group_id, "freq_unit": unit
                    }).execute()
            
            # --- จุดสำคัญ: บันทึกเสร็จแล้วสั่งพ่น Flex Message ทันที ---
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ มะมงบันทึกเรียบร้อย! กำลังสรุปยอดให้ครับเฮีย..."))
            trigger_bill_notification(group_id)
            
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"โฮ่ง! มะมงคำนวณพลาด: {str(e)}"))

if __name__ == "__main__": app.run(port=5000)