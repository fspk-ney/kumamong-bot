import os, pytz
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client, Client
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# --- Config (ห้ามแก้ Token/Secret) ---
LINE_ACCESS_TOKEN = "UXPznDfBmyuDMV/OX32Y6htg/EGdPjNEVoLvngkysgodSaLgUstA6ewbNcg7A0vJw5P4EUXHgRMhkxRBvpUYgB6Fp/ZgMpyRLtcL/4joySV5u5JSvOpQmq2qrHN+I1wZ/I7pw5zr9IolfsRyWoz+sQdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "a06d44bf8e6d6079c04d3ba052078e25"
supabase: Client = create_client("https://jvuhjuvvarpjcwpgwkny.supabase.co", "sb_publishable_H3wOadSnVy-bEwHt0Ls5kA_8V8Olboe")
line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route("/create_saving", methods=['POST'])
def create_saving():
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
        user_id = data['userId']
        group_id = data.get('groupId', 'personal')

        # คำนวณยอดต่อคนต่องวด
        num_people = len(t_ids)
        amount_per_person_per_period = round((total_project_amount / num_people) / total_installments, 2)
        base_time = datetime.strptime(f"{start_str} {time_str}", "%Y-%m-%d %H:%M")

        # บันทึกรายงวดลง Supabase
        for i in range(total_installments):
            if unit == "5_minutes": due_time = base_time + timedelta(minutes=i * 5)
            elif unit == "1d": due_time = base_time + timedelta(days=i)
            elif unit == "7d": due_time = base_time + timedelta(weeks=i)
            elif unit == "1m": due_time = base_time + relativedelta(months=i)
            else: due_time = base_time + timedelta(days=i)
            
            due_str = due_time.strftime('%Y-%m-%d %H:%M:%S')

            for tid, tname in zip(t_ids, t_names):
                supabase.table("bills").insert({
                    "bill_name": goal, "total_amount": total_project_amount,
                    "per_person": amount_per_person_per_period, "status": "pending",
                    "created_by": user_id, "freq_unit": unit, "next_due": due_str,
                    "remind_time": time_str, "target_user_id": tid,
                    "member_name": tname, "group_id": group_id
                }).execute()
        
        # --- จุดที่เฮียสั่ง: ให้บอทพ่นข้อความตอบกลับกลุ่มเองทันที ---
        target = group_id if group_id != 'personal' else user_id
        confirm_msg = f"🪙 บันทึกรายการสำเร็จ!\n📌 รายการ: {goal}\n💰 ยอดรวม: {total_project_amount:,.2f} บาท\n👥 สมาชิก: {data['targetNames']}\n\nมะมงรับทราบ! เดี๋ยวถึงเวลาทวงผมจัดให้ครับ โฮ่ง! 🐾"
        line_bot_api.push_message(target, TextSendMessage(text=confirm_msg))

        return "OK", 200
    except Exception as e:
        return str(e), 500

@app.route('/check_bills')
def check_bills():
    now = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%Y-%m-%d %H:%M:%S')
    res = supabase.table("bills").select("*").lte("next_due", now).eq("status", "pending").execute()
    
    if not res.data: return "No pending bills", 200

    for bill in res.data:
        target = bill.get('group_id') if bill.get('group_id') != 'personal' else bill['target_user_id']
        reminder = f"📢 มะมงมาทวงเงิน! รายการ: {bill['bill_name']}\n👤 ถึงคิวคุณ: {bill['member_name']}\n💰 ยอดงวดนี้: {bill['per_person']} บาท\nจ่ายด้วยนะเฮีย โฮ่ง! 🐾"
        try:
            line_bot_api.push_message(target, TextSendMessage(text=reminder))
            # แจ้งเตือนแล้วเปลี่ยนสถานะกันทวงซ้ำ
            supabase.table("bills").update({"status": "notified"}).eq("id", bill['id']).execute()
        except: pass
    return "Checked", 200

if __name__ == "__main__":
    app.run(port=5000)