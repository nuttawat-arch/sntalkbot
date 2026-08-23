# SN TalkBot 2026.08.23-r2 — Release Notes

## แก้ไขสำคัญ

- Player TTS announcement เปลี่ยนเป็น FIFO queue + worker เดียว ป้องกันเสียง "เพิ่มเข้าคิว" และ "กำลังเล่น" พูดซ้อนกัน
- แก้ Player-only logout callback ที่อาจเรียก `AccountRequestCog` ซึ่งไม่มีในโหมด Player และเกิด `AttributeError`
- ลบ public command aliases ที่ทำงานซ้ำกัน: `/h`, `/gl`, `/rs`, `/sd`
  - ใช้ `/help`, `/l`, `/restart`, `/shutdown` แทน
- validator เพิ่มการตรวจชื่อคำสั่งซ้ำและคำสั่งหลายชื่อที่ชี้ handler เดียวกันใน module เดียว

## Player TTS ใหม่

Player announcement TTS แยกจาก Server Manager TTS อย่างชัดเจน:

- `/ptts [on|off|status]`
- `/ptts tracks on|off`
- `/ptts queue on|off`
- `/pttsmode microsoft|google`
- `/pvoices [langcode]`
- `/pvoice <voice_name>`
- `/pttsrate <-100..100>` สำหรับ Microsoft
- `/pttsspeed <0.25..4.0>` สำหรับ Google

Google Player TTS ใช้ `[tts] google_api_key` แต่ voice/mode/speed ของ Player เก็บใน `[playback]` จึงไม่ปนกับ TTS ของ Server Manager

## Server Manager TTS

ชุดเดิมยังอยู่เฉพาะ Manager/Full เช่น `/say`, `/tts`, `/ttsmode`, `/voice`, `/get_voices`, `/rate`, `/pitch`, `/volume`, `/speed` และ `/st`

ถ้าสั่งเปลี่ยนเป็น Google ทั้งที่ยังไม่มี `google_api_key` ระบบจะปฏิเสธด้วยข้อความอธิบายแทนการ fallback แบบเงียบ ๆ

## Telegram Direct Report

- `/report <message>` ยังคงส่งหาแอดมิน TeamTalk และ register เฉพาะ Manager/Full
- เพิ่ม `/dr <message>` ทุกโหมด เพื่อส่งรายงานตรงไป Telegram
- รายงานประกอบด้วย TeamTalk server, bot/mode, nickname, username, channel และข้อความ
- ถ้า token/chat ID ไม่ครบ `/dr` จะตอบว่าไม่ได้ตั้งค่าและไม่ throw exception
- รองรับ environment `SNTALKBOT_TELEGRAM_BOT_TOKEN` และ `SNTALKBOT_TELEGRAM_REPORT_CHAT_ID` เพื่อไม่ต้องฝัง secret ใน Git/Docker image

## Validation

Static release validator ตรวจ:

- Python compile
- command name uniqueness
- same-handler alias duplication
- retired aliases
- Player TTS command set
- `/dr`
- `/help` parity
- `COMMANDS_TH.md` parity
- Thai message size
- Thai translations
- no legacy multi-profile references

หมายเหตุ: static/unit checks ไม่แทน live TeamTalk + PulseAudio + MPV + Google/Telegram network integration test บนเซิร์ฟเวอร์จริง
