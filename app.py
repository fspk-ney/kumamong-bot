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
def serve_index(): 
    return send_from_directory('.', 'index.html')

@app.route('/list')
def serve_list(): 
    return send_from_directory('.', 'list.html')

# --- 🚀 ระบบทวงเงินแบบใหม่ (รวบยอดเป็นบิลเดียวต่อกลุ่ม) ---
@app.route('/check_bills')
def check_bills():
    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    
    # 1. ดึงบิลทั้งหมด (ทั้งที่จ่ายแล้วและยังไม่จ่าย) เพื่อเอามาทำ List สถานะ
    res = supabase.table("bills").select("*").execute()
    if not res.data:
        return "No bills found", 200
    
    # 2. จัดกลุ่มบิลตามชื่อรายการและกลุ่ม
    grouped_bills = {}
    for bill in res.data:
        group_key = f"{bill['bill_name']}_{bill.get('group_id', 'personal')}"
        if group_key not in grouped_bills:
            grouped_bills[group_key] = []
        grouped_bills[group_key].append(bill)

    # 3. สร้าง Flex Message ใบเดียวที่มีรายละเอียดครบ
    for key, members in grouped_bills.items():
        try:
            bill_name = members[0]['bill_name']
            target_destination = members[0].get('group_id') or members[0].get('target_user_id') or members[0]['created_by']
            
            # เช็กว่าบิลนี้จ่ายครบทุกคนหรือยัง (ถ้าครบแล้วอาจจะไม่ต้องทวง)
            all_paid = all(m['status'] == 'paid' for m in members)
            if all_paid: continue 

            member_list_ui = []
            for m in members:
                is_paid = m['status'] == 'paid'
                icon = "✅" if is_paid else "⏳"
                color = "#1DB446" if is_paid else "#ff4d4d"
                status_text = "จ่ายแล้ว" if is_paid else "ยังไม่จ่าย"

                member_list_ui.append({
                    "type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": f"{icon} {m['member_name']}", "size": "sm", "color": "#111111", "flex": 4},
                        {"type": "text", "text": status_text, "size": "xs", "color": color, "align": "end", "flex": 2}
                    ]
                })

            flex = {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "text", "text": "💰 รายละเอียดบิลกลุ่ม", "weight": "bold", "color": "#1DB446", "size": "sm"},
                        {"type": "text", "text": bill_name, "weight": "bold", "size": "xl", "margin": "md"},
                        {"type": "text", "text": f"ยอดต่อคน: {members[0]['per_person']:,.2f} บาท", "size": "xs", "color": "#888888"},
                        {"type": "separator", "margin": "lg"},
                        {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "xs", "contents": member_list_ui},
                        {"type": "separator", "margin": "lg"},
                        {"type": "text", "text": "* อัปเดตสถานะล่าสุดเมี๊ยว 🐾", "size": "xs", "color": "#aaaaaa", "margin": "md"}
                    ]
                },
                "footer": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "button", "style": "primary", "color": "#1DB446", "action": {
                            "type": "uri", "label": "✅ แจ้งจ่ายเงิน / ดูทั้งหมด", "uri": f"https://liff.line.me/{MY_LIFF_ID}/list"
                        }}
                    ]
                }
            }
            
            line_bot_api.push_message(target_destination, FlexSendMessage(alt_text=f"อัปเดตบิล {bill_name}", contents=flex))

        except Exception as e:
            print(f"Error: {e}")
            
    return "Check Complete", 200

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
    data_str = event.postback.data
    params = dict(x.split('=') for x in data_str.split('&'))
    if params.get('action') == 'pay':
        bill_id = params['bill_id']
        bill_name = params.get('name', 'รายการออม')
        supabase.table("bills").update({"status": "paid"}).eq("id", bill_id).execute()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 บันทึกว่าคุณจ่าย '{bill_name}' เรียบร้อยแล้วเมี๊ยว! 🐾"))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id
    
    source = event.source
    if hasattr(source, 'group_id'):
        group_id = source.group_id
    elif hasattr(source, 'room_id'):
        group_id = source.room_id
    else:
        group_id = 'personal'

    try:
        profile = line_bot_api.get_profile(user_id)
        display_name = profile.display_name
        supabase.table("group_members").upsert({"group_id": group_id, "user_id": user_id, "display_name": display_name}).execute()
    except Exception as e:
        print(f"Profile error: {e}")

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
            
            t_ids = [i.strip() for i in lines[7].split(': ')[1].split(',')]
            t_names = [n.strip() for n in lines[8].split(': ')[1].split(',')]

            per_person = round(total / count, 2)
            
            for target_id, target_name in zip(t_ids, t_names):
                data = {
                    "bill_name": goal, 
                    "total_amount": total, 
                    "per_person": per_person,
                    "status": "pending", 
                    "created_by": user_id, 
                    "freq_unit": unit,
                    "next_due": start, 
                    "remind_time": time, 
                    "target_user_id": target_id, 
                    "member_name": target_name,
                    "group_id": group_id
                }
                supabase.table("bills").insert(data).execute()
            
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ บันทึกบิล '{goal}' เรียบร้อย! คุ้มมงจะคอยทวงทุกคนในกลุ่มให้เองเมี๊ยว!"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"เกิดข้อผิดพลาด: {str(e)}"))

if __name__ == "__main__": 
    app.run(port=5000)