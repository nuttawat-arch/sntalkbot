# ผลตรวจ 3 ฐาน: SNTalkBot / TTMediaBot-th / TtManager

## หลักการแยกโหมด
- Full Bot: Common + Player + Server Manager
- Player Bot: Common + Player เท่านั้น
- Server Manager Bot: Common + Manager เท่านั้น

## สิ่งที่นำกลับมา
- พฤติกรรม unknown command ของ TTMediaBot: ตอบทาง Private และแนะนำ `h`
- Common alias: `a -> about`
- Player legacy aliases: `gl -> l`, `c -> select`, `sb -> -`, `sf -> +`
- Manager aliases ที่คงไว้หลังจัดรูปแบบใหม่: `j -> join`, `sc -> save`, `vt -> voicetx`; `jc`/`va` ถูกตัดเพราะซ้ำ intent
- สถานะตามประเภทบอต + `พิมพ์ h เพื่อดูวิธีใช้`

## สิ่งที่ไม่ย้อนกลับ
- `sv` service abstraction เก่า: ระบบปัจจุบันใช้ `p`, `pm`, `u` โดยตรง
- `f` แบบ favorites เก่า: ปัจจุบัน `f` คือ fade และมี `fav`/`favorites` แยกแล้ว
- `q` แบบ quit เก่า: ปัจจุบัน `q` คือ queue; การปิดบอตใช้ `shutdown`/`sd`
- `l` แบบ lock เก่า: Player ใช้ `l` ขอ URL เพลง; Manager ใช้ canonical `lock` เพื่อไม่ชน Full Bot
- `cl` แบบ language เก่า: ปัจจุบัน `cl` คือ clearlog; language ใช้ `language`/`lg`
- Google Cloud TTS/credential flow เก่า: ไม่คืน ระบบปัจจุบันใช้ Microsoft หรือ Google standard gTTS ตามค่าปัจจุบัน
- event/service/ban-list implementations เก่าที่ไม่มี parity ชัดเจน: ไม่คัดลอกทับระบบใหม่

## about / dr
`about` ไม่แสดง URL ของหน้า report service เพราะผู้ใช้เข้าไปแล้วไม่มีแบบฟอร์ม โดยแนะนำ `dr <ข้อความของคุณ>` สำหรับแจ้งบั๊ก รายงานปัญหา ขอฟีเจอร์ หรือเสนอแนะฟีเจอร์แทน API ภายในยังคงใช้สำหรับส่ง `dr` โดยตรงและไม่ถือเป็นลิงก์สำหรับผู้ใช้
