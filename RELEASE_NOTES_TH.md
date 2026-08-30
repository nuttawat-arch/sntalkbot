# SNTalkBot 5.1.20 — Selection Intent + Thai Update + Telegram Ownership

- แก้ `p <คำค้น>` ฝั่ง YouTube ทั้ง Queue Mode และโหมดปกติ: ใช้ YouTube Search URL extractor เป็นทางหลักและ fallback ไป `ytsearch:` หากผลลัพธ์แรกว่าง; `pm` ยังคงใช้ YouTube Music แยกต่างหาก
- `select <index>` / `c <index>` มีหน้าที่เดียว: กระโดดไปเพลง/รายการลำดับที่ระบุใน Queue หรือ playlist/session ที่กำลังใช้งานเท่านั้น ไม่เลือกผลค้นหาโดยอ้อมอีกต่อไป
- ผลค้นหายังคงใช้คำสั่ง `.` และ `,` สำหรับเปลี่ยนผลทีละรายการ จึงไม่มีสอง action แย่งความหมายของคำสั่งเดียวกัน
- การแจ้ง GitHub Release เข้า TeamTalk เปลี่ยนเป็นข้อความภาษาไทยแบบสั้นและไม่แนบ URL ของ GitHub
- Telegram ของแต่ละ instance มีสิทธิ์เหนือ Telegram ส่วนกลาง: ถ้าเจ้าของใส่ `telegram_bot_token` ของตนเอง ระบบใช้ token + default Chat ID ของ instance นั้นเท่านั้น และไม่ผสมค่า Telegram กลาง
- Telegram ส่วนกลางใช้เฉพาะ instance ที่ไม่ได้กำหนด token ของตัวเอง
- คง Queue true-skip จาก 5.1.19: `c 10` เล่นรายการ 10 และต่อ 11 โดยไม่ย้อนกลับรายการ 1
