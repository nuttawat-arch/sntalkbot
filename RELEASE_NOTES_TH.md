# Release notes — 2026.08.23-r4

- แก้ Player TTS announcement ไม่ให้ลด/duck/พักเพลงอีกต่อไป
- TTS announcement ใช้ libmpv แยก stream แล้ว mix กับเพลงผ่าน PulseAudio sink เดียวกัน
- เพลงรักษา volume เดิมตลอดระหว่างข้อความ “เพิ่มเพลงเข้าคิว”, “กำลังเล่น” และประกาศ Player อื่น ๆ
- คง FIFO announcement queue จาก r3 เพื่อให้ TTS หลายข้อความไม่พูดซ้อนกันเอง
- คง Google standard gTTS เป็นค่าเริ่มต้นทั้ง Player และ Manager

# SN TalkBot 2026.08.23-r3 — Google Standard TTS

## เปลี่ยน TTS หลัก

- ตัด Google Cloud Text-to-Speech ออกจาก runtime และลบ `bot/GoogleCloudTTSClient.py`
- โหมด `google` ใช้ `gTTS` (Google Translate TTS แบบมาตรฐาน) ไม่ต้องใช้ API key
- Player และ Server Manager ตั้ง Google standard เป็นค่าเริ่มต้นทั้งคู่
- ค่าเริ่มต้นภาษาไทยคือ `th`
- `/voice` และ `/pvoice` ใน Google mode ใช้รหัสภาษา เช่น `th`, `en`, `ja` แทนชื่อ Cloud voice
- `/get_voices` และ `/pvoices` ใน Google mode แสดงภาษาที่ gTTS รองรับ
- `/speed` และ `/pttsspeed` ยังรองรับ `0.25..4.0` โดยใช้ FFmpeg `atempo`
- Microsoft Edge TTS ยังอยู่เป็น engine สำรอง ไม่ได้ลบออก
- มี migration ครั้งเดียวสำหรับ config r2: ลบ key Google Cloud เก่าและเปลี่ยนค่าเริ่มต้นทั้ง Manager/Player เป็น gTTS
- FIFO Player announcement จาก r2 ยังคงอยู่ จึงยังพูดทีละข้อความไม่ซ้อนกัน

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

หมายเหตุประวัติ r2: รุ่นนั้นเคยใช้ Google Cloud สำหรับโหมด Google; r3 ยกเลิกแนวทางนี้แล้วและใช้ gTTS มาตรฐานแทน

## Server Manager TTS

ชุดเดิมยังอยู่เฉพาะ Manager/Full เช่น `/say`, `/tts`, `/ttsmode`, `/voice`, `/get_voices`, `/rate`, `/pitch`, `/volume`, `/speed` และ `/st`

หมายเหตุประวัติ r2: พฤติกรรม API key นี้ถูกยกเลิกใน r3 เพราะ Google mode ไม่ต้องใช้ API key แล้ว

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
