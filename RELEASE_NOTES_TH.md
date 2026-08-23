# 2026.08.23-r7.4.3

- แก้ Linux TeamTalk runtime: ข้อความขาเข้าจาก SDK อาจเป็น `bytes`; แปลง UTF-8 เป็น `str` ก่อน Unicode normalization/command parsing
- แก้อาการส่งคำสั่งทั้งแบบมี `/` และไม่มี `/` แล้วบอตเงียบ พร้อมป้องกัน event-loop `TypeError: normalize() argument 2 must be str, not bytes`
- ตัวกรองคำหยาบใช้ตัวถอดข้อความเดียวกัน จึงรองรับภาษาไทยจาก TeamTalk Linux จริง ไม่ใช่เฉพาะ test ที่จำลองเป็น `str`
- เพิ่ม regression test ให้จำลอง Linux `ttstr()` ที่คืน bytes เพื่อไม่ให้บั๊กนี้ผ่าน validator อีก

# SNTalkBot 2026.08.23-r7.4.2

- แก้ regression ของ r7.4.1: คืนคำสั่ง prefix-free ให้ใช้ได้ทั้ง Private และ Channel/Broadcast เช่น `h`, `p เพลง`, `ap on`, `ci off`, `filter on`; `/` เป็นเพียง compatibility และไม่บังคับ
- ย้ายรายการคำหยาบภาษาไทยเข้า `blacklist.txt` เดียวกับภาษาอังกฤษ/อาหรับและรายการเดิมทั้งหมด โดยคง `badword.txt` ไว้เป็น supplemental compatibility เพื่อไม่รื้อของเก่า
- ทำ `filter on|off|status` เป็น master switch ของ word moderation: ปิด/เปิด blacklist และ badword พร้อมกัน รวมข้อความ ชื่อผู้ใช้ และชื่อ/หัวข้อ Channel
- แก้ blacklist matcher ให้รองรับภาษาไทย/Unicode และรูปแบบเว้นวรรค เช่น `ค ว ย` พร้อมป้องกัน false positive คำสั้นอย่าง `หี` ไม่จับ `หีบ`
- แก้กรณี `files/blacklist.wav` ไม่มีในแพ็กเกจ: เสียงเตือนเป็น optional และไม่สามารถทำให้การเตะ/แบนหยุดด้วย exception ได้อีก
- คงลำดับ moderation ก่อน `ci` ดังนั้น `ci off` ปิดการตอบสนองปกติใน Channel แต่ไม่ปิดตัวกรองที่เปิดอยู่; ใช้ `filter off` เมื่อต้องการปิดการกรองทั้งหมด
- สถานะอัตโนมัติกลับเป็นแบบสั้น `พิมพ์ h เพื่อดูคำสั่ง` โดยยังรู้จักสถานะ r7.4.1 เพื่อ migration

# Release 2026.08.23-r7.4.1

- แก้ regression จากชุด r7.4 pre-release: คำสั่งแบบไม่ใส่ `/` ใช้เฉพาะ Private; Channel/Broadcast บังคับ `/` ทุกคำสั่ง เช่น Private `h`, `p เพลง`, `ci off` แต่ในห้องใช้ `/h`, `/p เพลง`, `/ci off`
- คง parser แบบสั้นตาม TTMediaBot สำหรับ Private พร้อม Unicode normalization เพื่อรองรับอักขระ format/control ที่อาจติดมาจากช่องข้อความ
- ปรับสถานะอัตโนมัติให้บอกสั้นและชัดตามบริบท: `ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h` โดยยัง migrate ข้อความสถานะอัตโนมัติรุ่นเก่าได้
- `ci off` ปิดเฉพาะ command/TTS/Player/translation จาก Channel แต่ moderation/blacklist/ตัวกรองคำหยาบยังทำงานกับข้อความที่บอตได้รับ; Private ยังใช้ `ci on` เพื่อเปิดกลับได้เสมอ
- `intercept on|off|status` คำสั่งย่อ `ic` สำหรับ Manager/Full ยังเปิด/ปิดการดักข้อความจากทุก Channel แบบ runtime และบันทึกค่าใน config ตามเดิม
- `filter on|off|status` และ `badword.txt` ภาษาไทยยังทำงานก่อน `ci` พร้อม matcher รูปเว้นวรรค/อักขระแฝงและการลด false positive ของคำสั้น
- `about`/`ab` และ `dr <ข้อความ>` คงข้อมูลผู้พัฒนา/ช่องทาง report service ตามชุด r7.4
- คำสั่งหลัก 121 คำสั่ง และ alias 47 ตัว; validator เพิ่ม regression test บังคับว่า plain channel text เช่น `h`, `s`, `p เพลง`, `ap on` ต้องไม่ถูก dispatch และรูปแบบ `/...` เท่านั้นที่ทำงานใน Channel

---

# Release 2026.08.23-r7.3.1

- Hotfix การอัปเกรด config สำหรับ Docker instance เดิม: setting ใหม่ที่เป็น optional จะเติมค่า default ลง `config.ini` อัตโนมัติก่อน validation
- แก้ปัญหา r7.3 ที่ instance เดิมไม่มี `channel_input_enabled` แล้วถูกส่งเข้า interactive setup wizard ใน container แบบ detached ทำให้บอตไม่ถึงขั้น login TeamTalk
- `channel_input_enabled` ของ config เก่าจะถูกเพิ่มเป็น `True` อัตโนมัติ โดยรักษาค่าเดิมอื่นทั้งหมด
- ถ้าค่าที่จำเป็นจริง ๆ หายและไม่มี interactive terminal ระบบจะแจ้งชื่อ `[section] key` ที่ขาดอย่างชัดเจนแทนการล้มด้วย EOF
- เพิ่ม validator จำลอง config เก่าจริงเพื่อกัน regression นี้ใน release ต่อไป
- ฟีเจอร์ r7.3 (`ci`, `cm`, คำสั่งรูปแบบเดียวกันใน Private + Channel) คงเดิมทั้งหมด

---

# Release 2026.08.23-r7.3

- เปลี่ยนคำสั่งให้ใช้รูปแบบเดียวกันทั้ง Private และ Channel เช่น `h`, `s`, `p เพลง`
- เพิ่ม `channelinput on|off|status` คำสั่งย่อ `ci` สำหรับผู้ดูแล
  - `ci off` = บอตไม่อ่านและไม่ตอบสนองต่อข้อความจาก Channel ทั้งหมด
  - Private Message ยังทำงาน จึงใช้ `ci on` ทาง Private เพื่อเปิด Channel กลับได้เสมอ
- ขยาย `cm` เป็น `cm on|off|status` และยังรองรับ `cm` เปล่าเพื่อสลับสถานะแบบเดิม
  - `cm off` ปิดข้อความ Player ที่ประกาศลง Channel เช่น ใครเปิดเพลงหรือเพิ่มเพลงเข้าคิว
  - ไม่กระทบการรับคำสั่ง; `ci` และ `cm` แยกจากกัน
- เพิ่ม config `channel_input_enabled = True` และบันทึกค่าที่เปลี่ยนจากคำสั่งลง `config.ini`
- สถานะอัตโนมัติย่อเป็น `พิมพ์ h เพื่อดูคำสั่ง`
- Validator เพิ่ม regression test สำหรับคำสั่งตรงใน Private + Channel, Channel Input OFF, alias/argument และความคงอยู่ของ config
- คำสั่งหลักรวม 120 คำสั่ง และ alias 46 ตัว

---

# 2026.08.23-r7.1

- สถานะเริ่มต้นระบุประเภทบอตอัตโนมัติ: Player Bot, Server Manager Bot หรือ Full Bot
- config เก่าที่ใช้ `status_message = SN TalkBot` จะได้รับสถานะตามประเภทโดยไม่ต้องแก้ config เอง
- สถานะที่ผู้ดูแลตั้งเองยังคงใช้ตามเดิม และ `cs auto` ใช้กลับสู่สถานะอัตโนมัติ
- เมื่อ Player หยุดเพลงหรือเปิดการแสดงสถานะกลับมา ระบบคืนสถานะประเภทบอตอย่างถูกต้อง

# Release 2026.08.23-r7

- เริ่มรองรับการพิมพ์คำสั่งโดยตรงในข้อความส่วนตัว เช่น `help`, `ap on`, `wb off`, `rs`
- alias ส่ง argument ต่อเหมือนคำสั่งหลัก จึงใช้ `ap on`, `ap off`, `wb on`, `wb off`, `acs on`, `vt off` ได้
- การ block คำสั่งหลักยัง block alias ของคำสั่งนั้นด้วย และ `blockcmd` หรือ `bc` ยัง resolve alias เป็นคำสั่งหลัก
- เพิ่ม regression test สำหรับคำสั่งส่วนตัวและ on/off ผ่าน alias
- `help` แสดงคำสั่งแบบตรงเป็นรูปแบบหลัก

# SNTalkBot 2026.08.23-r6

## แก้ไขหลัก

- Welcome broadcast และ welcome ตอนเข้าห้องไม่ประกาศย้อนหลังให้ผู้ใช้ที่ออนไลน์อยู่ก่อนบอตเริ่มหรือ reconnect
- ผู้ใช้ที่อยู่ในชุด startup sync จะถูกกันไว้จน logout ป้องกัน event ซ้ำที่มาช้ากว่าเวลา bootstrap
- เพิ่มระบบคำสั่งย่อผ่าน alias resolver โดยไม่ลงทะเบียน command handler ซ้ำ
- คำสั่งย่อสำคัญ เช่น `h` → `help`, `rs` → `restart`, `sd` → `shutdown` และคำสั่งย่ออื่นจะแสดงใน `help`
- `cc`, `csize`, `cm` อยู่ใน PlayerCog เท่านั้น จึงไม่โผล่ใน Server Manager
- แก้ `split_long_message()` ไม่ให้ข้อความช่วงรอยต่อหายเมื่อแบ่งที่ช่องว่าง
- เพิ่ม guard ในงาน Player/Weather/SSH บางส่วนเมื่อผู้ใช้ออกจาก TeamTalk ระหว่างงาน async
- blocked command ที่เคยบันทึกด้วยชื่อ alias จะถูก normalize กลับเป็นชื่อคำสั่งหลัก
- คง Google standard gTTS, FIFO Player TTS, No Music Ducking และ `dr` จาก r5

## การตรวจสอบ

- Python compile
- ชื่อคำสั่งหลักไม่ซ้ำ
- alias ไม่ชนชื่อคำสั่งหลักและ target ต้องมีจริง
- Player/Manager role-specific commands ไม่ชนกัน
- `help` และ `COMMANDS_TH.md` ตรงกับคำสั่งหลักที่ลงทะเบียน
- ไม่มี Telegram bot token ในไฟล์ release

# SNTalkBot 2026.08.23-r5

- `dr` เปลี่ยนเป็นระบบรายงานถึงผู้พัฒนาแบบ relay กลางที่ `https://report.nuttawat.ddnsfree.com/api/report`
- ไม่ต้องและไม่ควรฝัง Telegram Bot Token ใน Docker image หรือ config ของลูกค้า
- API ล่ม/timeout แล้วคำสั่งจบอย่างปลอดภัย ไม่ทำให้บอต crash
- จำกัดข้อความ `dr` สูงสุด 2000 ตัวอักษร
- `about` อ่านเวอร์ชันจากไฟล์ VERSION จริง ไม่ hard-code รุ่นเก่า
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
- `voice` และ `pvoice` ใน Google mode ใช้รหัสภาษา เช่น `th`, `en`, `ja` แทนชื่อ Cloud voice
- `get_voices` และ `pvoices` ใน Google mode แสดงภาษาที่ gTTS รองรับ
- `speed` และ `pttsspeed` ยังรองรับ `0.25..4.0` โดยใช้ FFmpeg `atempo`
- Microsoft Edge TTS ยังอยู่เป็น engine สำรอง ไม่ได้ลบออก
- มี migration ครั้งเดียวสำหรับ config r2: ลบ key Google Cloud เก่าและเปลี่ยนค่าเริ่มต้นทั้ง Manager/Player เป็น gTTS
- FIFO Player announcement จาก r2 ยังคงอยู่ จึงยังพูดทีละข้อความไม่ซ้อนกัน

# SN TalkBot 2026.08.23-r2 — Release Notes

## แก้ไขสำคัญ

- Player TTS announcement เปลี่ยนเป็น FIFO queue + worker เดียว ป้องกันเสียง "เพิ่มเข้าคิว" และ "กำลังเล่น" พูดซ้อนกัน
- แก้ Player-only logout callback ที่อาจเรียก `AccountRequestCog` ซึ่งไม่มีในโหมด Player และเกิด `AttributeError`
- ลบ public command aliases ที่ทำงานซ้ำกัน: `h`, `gl`, `rs`, `sd`
  - ใช้ `help`, `l`, `restart`, `shutdown` แทน
- validator เพิ่มการตรวจชื่อคำสั่งซ้ำและคำสั่งหลายชื่อที่ชี้ handler เดียวกันใน module เดียว

## Player TTS ใหม่

Player announcement TTS แยกจาก Server Manager TTS อย่างชัดเจน:

- `ptts [on|off|status]`
- `ptts tracks on|off`
- `ptts queue on|off`
- `pttsmode microsoft|google`
- `pvoices [langcode]`
- `pvoice <voice_name>`
- `pttsrate <-100..100>` สำหรับ Microsoft
- `pttsspeed <0.25..4.0>` สำหรับ Google

หมายเหตุประวัติ r2: รุ่นนั้นเคยใช้ Google Cloud สำหรับโหมด Google; r3 ยกเลิกแนวทางนี้แล้วและใช้ gTTS มาตรฐานแทน

## Server Manager TTS

ชุดเดิมยังอยู่เฉพาะ Manager/Full เช่น `say`, `tts`, `ttsmode`, `voice`, `get_voices`, `rate`, `pitch`, `volume`, `speed` และ `st`

หมายเหตุประวัติ r2: พฤติกรรม API key นี้ถูกยกเลิกใน r3 เพราะ Google mode ไม่ต้องใช้ API key แล้ว

## Telegram Direct Report

- `report <message>` ยังคงส่งหาแอดมิน TeamTalk และ register เฉพาะ Manager/Full
- เพิ่ม `dr <message>` ทุกโหมด เพื่อส่งรายงานตรงไป Telegram
- รายงานประกอบด้วย TeamTalk server, bot/mode, nickname, username, channel และข้อความ
- ถ้า token/chat ID ไม่ครบ `dr` จะตอบว่าไม่ได้ตั้งค่าและไม่ throw exception
- รองรับ environment `SNTALKBOT_TELEGRAM_BOT_TOKEN` และ `SNTALKBOT_TELEGRAM_REPORT_CHAT_ID` เพื่อไม่ต้องฝัง secret ใน Git/Docker image

## Validation

Static release validator ตรวจ:

- Python compile
- command name uniqueness
- same-handler alias duplication
- retired aliases
- Player TTS command set
- `dr`
- `help` parity
- `COMMANDS_TH.md` parity
- Thai message size
- Thai translations
- no legacy multi-profile references

หมายเหตุ: static/unit checks ไม่แทน live TeamTalk + PulseAudio + MPV + Google/Telegram network integration test บนเซิร์ฟเวอร์จริง
