@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    
    # เมื่อได้รับข้อความจากหน้าป๊อปอัพ (LIFF)
    if "[คำสั่งออมเงิน]" in text:
        try:
            lines = text.split('\n')
            goal_name = lines[1].split(': ')[1]
            total = float(lines[2].split(': ')[1])
            freq = lines[3].split(': ')[1]
            
            # คำนวณเบื้องต้น (สมมติหาร 2 คนตามที่เฮียเคยบอก หรือจะให้เพื่อนกดจอยเพิ่มทีหลัง)
            per_person_total = total / 2
            per_installment = round(per_person_total / 36, 2)
            
            reply_text = (
                f"🐾 คุ้มมงเปิดบิลออมเงินแล้วเมี๊ยว!\n\n"
                f"📌 เป้าหมาย: {goal_name}\n"
                f"💰 ยอดรวม: {total:,.2 text} บาท\n"
                f"⏰ ความถี่: {freq}\n"
                f"🔢 ทั้งหมด: 36 งวด\n"
                f"----------------------\n"
                f"💵 เก็บคนละประมาณ: {per_installment:,.2f} บาท/งวด\n"
                f"(คำนวณเบื้องต้นสำหรับสมาชิก 2 คน)\n\n"
                f"เตรียมเงินไว้ให้ดี อย่าให้คุ้มมงต้องกางเล็บ! 🐱"
            )
        except Exception as e:
            reply_text = "เกิดข้อผิดพลาดในการคำนวณเมี๊ยว! ลองตั้งค่าใหม่อีกทีนะเฮีย"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    
    # คำสั่งเรียกหน้าป๊อปอัพ (พิมพ์คำนี้เพื่อเปิดหน้าเลือก)
    elif text == "สร้างบิล":
        liff_url = f"https://liff.line.me/2009693749-SfmWsP0l"
        reply_text = f"จิ้มที่ลิงก์เพื่อตั้งค่าบิลออมเงินเลยเมี๊ยว! 🐾\n{liff_url}"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )