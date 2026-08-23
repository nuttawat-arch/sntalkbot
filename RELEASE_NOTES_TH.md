# 2026.08.23-r7.2.1

- แก้คำสั่ง Private แบบไม่ใส่ `/` ให้รองรับทั้ง TeamTalk `MSGTYPE_USER` และ `MSGTYPE_CUSTOM` เช่น `h`, `s`, `p <คำค้นหา>`, `ap on|off`
- ใน Channel ยังคงต้องใส่ `/` ทุกคำสั่ง เช่น `/h`, `/s`, `/p <คำค้นหา>`
- เพิ่ม regression test ครอบคลุม private custom-message ของ TeamTalk เพื่อป้องกันอาการ validator ผ่านแต่ runtime ไม่รับ slashless

# Release notes — 2026.08.23-r7.2

- ปรับสถานะเริ่มต้นให้บอกวิธีดูคำสั่งตามบริบท: `ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h`
- ยืนยันกติกาคำสั่ง: Private Message ใช้คำสั่งโดยไม่ใส่ `/` ได้ ส่วน Channel/Broadcast ต้องใส่ `/` ทุกคำสั่ง
- `/h` และ `h` ชี้ไปคำสั่ง `help` เดียวกัน โดย argument ของ alias ยังส่งต่อเหมือนเดิม
- เพิ่ม regression test โดยตรงสำหรับ `h` ใน Private, `h` ใน Channel, `/h` ใน Channel และ `ap on/off`
- สถานะอัตโนมัติแบบ r7.1 ที่มีคำว่า `พิมพ์ help เพื่อดูคำสั่ง` จะถูกมองเป็นสถานะ legacy และอัปเกรดเป็นข้อความใหม่โดยไม่ทับ custom status ของผู้ดูแล

## 2026.08.23-r7.1

- สถานะเริ่มต้นระบุประเภทบอตอัตโนมัติ: Player Bot, Server Manager Bot หรือ Full Bot
- config เก่าที่ใช้ `status_message = SN TalkBot` จะได้รับสถานะตามประเภทโดยไม่ต้องแก้ config เอง
- สถานะที่ผู้ดูแลตั้งเองยังคงใช้ตามเดิม และ `cs auto` ใช้กลับสู่สถานะอัตโนมัติ
- เมื่อ Player หยุดเพลงหรือเปิดการแสดงสถานะกลับมา ระบบคืนสถานะประเภทบอตอย่างถูกต้อง

# Release 2026.08.23-r7

- คำสั่งในข้อความส่วนตัวไม่ต้องมี `/` นำหน้าแล้ว เช่น `help`, `ap on`, `wb off`, `rs`
- รูปแบบเดิมที่มี `/` ยังใช้ได้ทั้งหมดเพื่อไม่ให้ config/คู่มือ/ผู้ใช้เดิมพัง
- คำสั่งแบบไม่ใส่ `/` จำกัดเฉพาะข้อความส่วนตัว เพื่อไม่ให้คำสั่งย่ออย่าง `m`, `w`, `h`, `l` ชนกับข้อความสนทนาในห้อง
- alias ส่ง argument ต่อเหมือนคำสั่งหลัก จึงใช้ `ap on`, `ap off`, `wb on`, `wb off`, `acs on`, `vt off` ได้
- การ block คำสั่งหลักยัง block alias ของคำสั่งนั้นด้วย และ `blockcmd`/`bc` ยัง resolve alias เป็นคำสั่งหลัก
- เพิ่ม regression test สำหรับ slashless private command, on/off ผ่าน alias, backward compatibility ของ `/command` และการไม่จับ plain text ใน channel
- `/help` แสดงคำสั่งแบบไม่ใส่ `/` เป็นรูปแบบหลัก

# SNTalkBot 2026.08.23-r6

## แก้ไขหลัก

- Welcome broadcast และ welcome ตอนเข้าห้องไม่ประกาศย้อนหลังให้ผู้ใช้ที่ออนไลน์อยู่ก่อนบอตเริ่มหรือ reconnect
- ผู้ใช้ที่อยู่ในชุด startup sync จะถูกกันไว้จน logout ป้องกัน event ซ้ำที่มาช้ากว่าเวลา bootstrap
- เพิ่มระบบคำสั่งย่อผ่าน alias resolver โดยไม่ลงทะเบียน command handler ซ้ำ
- คำสั่งย่อสำคัญ เช่น `/h` → `/help`, `/rs` → `/restart`, `/sd` → `/shutdown` และคำสั่งย่ออื่นจะแสดงใน `/help`
- `/cc`, `/csize`, `/cm` อยู่ใน PlayerCog เท่านั้น จึงไม่โผล่ใน Server Manager
- แก้ `split_long_message()` ไม่ให้ข้อความช่วงรอยต่อหายเมื่อแบ่งที่ช่องว่าง
- เพิ่ม guard ในงาน Player/Weather/SSH บางส่วนเมื่อผู้ใช้ออกจาก TeamTalk ระหว่างงาน async
- blocked command ที่เคยบันทึกด้วยชื่อ alias จะถูก normalize กลับเป็นชื่อคำสั่งหลัก
- คง Google standard gTTS, FIFO Player TTS, No Music Ducking และ `/dr` จาก r5

## การตรวจสอบ

- Python compile
- ชื่อคำสั่งหลักไม่ซ้ำ
- alias ไม่ชนชื่อคำสั่งหลักและ target ต้องมีจริง
- Player/Manager role-specific commands ไม่ชนกัน
- `/help` และ `COMMANDS_TH.md` ตรงกับคำสั่งหลักที่ลงทะเบียน
- ไม่มี Telegram bot token ในไฟล์ release

# SNTalkBot 2026.08.23-r5

- `/dr` เปลี่ยนเป็นระบบรายงานถึงผู้พัฒนาแบบ relay กลางที่ `https://report.nuttawat.ddnsfree.com/api/report`
- ไม่ต้องและไม่ควรฝัง Telegram Bot Token ใน Docker image หรือ config ของลูกค้า
- API ล่ม/timeout แล้วคำสั่งจบอย่างปลอดภัย ไม่ทำให้บอต crash
- จำกัดข้อความ `/dr` สูงสุด 2000 ตัวอักษร
- `/about` อ่านเวอร์ชันจากไฟล์ VERSION จริง ไม่ hard-code รุ่นเก่า
- คง Google standard gTTS และ FIFO TTS จาก r3
- คง No Music Ducking จาก r4: TTS Player ไม่ปรับ volume เพลง

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
