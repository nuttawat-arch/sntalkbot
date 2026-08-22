# รายงานการรวมและที่มาของ SNTalkBot

รุ่น: 2026.08.22

## ฐานโปรเจกต์

ใช้ `tt_utilities-nut` เป็นฐาน เพราะมีโมดูลและคำสั่งมากกว่า `tt_utilities-main` แล้วคัดเฉพาะส่วนที่แข็งแรงกว่าหรือขาดอยู่จาก `main` มารวม โดยไม่คงระบบหลายโปรไฟล์

จาก `TTMediaBot-th` นำแนวคิดที่เหมาะกับบอตหลักมาเสริม ได้แก่ prefetch worker, PulseAudio virtual sink สำหรับ Linux/Docker, การ block คำสั่งเป็นรายคำสั่ง, reconnect ที่ตั้งค่าได้, helper สำหรับ Channel ID, การจัดการ cache และฟังก์ชัน player/queue ที่ช่วยเพิ่มความแข็งแรง

ไม่ได้คัดลอก service เก่าที่พึ่ง `py-yt-search`, โมดูล VK/Yandex ที่ต้องมี credential เพิ่ม และ dynamic Python event loader ที่เปิดช่องให้โหลดโค้ด arbitrary บน production bot

## ระบบคำสั่ง

- คำสั่งที่ลงทะเบียนจริง: 116 คำสั่ง
- ชื่อคำสั่งไม่ซ้ำกัน: 116/116
- ทุกคำสั่งต้องขึ้นต้นด้วย `/`
- ข้อความธรรมดาที่ไม่ขึ้นต้น `/` จะไม่ถูกตีความเป็นคำสั่ง
- `/help` และ `/h` ส่งหัวข้อก่อน 1 ข้อความ จากนั้นส่งหนึ่งคำสั่งพร้อมคำอธิบายต่อหนึ่ง TeamTalk private message
- `COMMANDS_TH.md` ตรงกับคำสั่งที่ลงทะเบียนจริง 116/116
- บรรทัดภาษาไทยที่ยาวที่สุด 429 UTF-8 bytes ต่ำกว่าขีดแบ่งข้อความภายใน 480 bytes

## Player และ YouTube

- ใช้ yt-dlp Python API โดยตรง
- YouTube: `/p`
- YouTube Music: `/pm`
- URL/playlist/channel/queue/favorites/autoplay
- M1 Single, M2 Auto/Next, M3 Repeat
- TTS ประกาศเพลง/คิว พร้อม ducking เสียงเพลงขณะประกาศ
- prefetch รายการถัดไปใน worker แยก เพื่อลดการบล็อก TeamTalk event thread
- cache/temp cleanup และ cache size ใช้กับ player รุ่นรวมจริง
- MPV ใช้งานแบบไม่มี GUI โดยส่งเสียงเข้าระบบ PulseAudio bridge

## Linux และ Docker

เส้นทางเสียงที่ออกแบบไว้คือ:

`MPV -> PulseAudio null sink (ttutilities) -> monitor source -> TeamTalk input`

จึงไม่ใช้ audio output แบบ null ที่ทิ้งเสียง เพราะบอตต้องส่งเสียงเพลงจริงเข้าสู่ TeamTalk

มีไฟล์:

- `run_linux.sh`
- `tools/setup_pulse_bridge.sh`
- `sntalkbot.service`
- `Dockerfile`
- `docker-compose.yml`
- `docker-entrypoint.sh`
- `tools/check_environment.py`
- `tools/download_teamtalk_sdk.py`
- `tools/install_teamtalk_sdk.py`

Docker target หลักเป็น Linux amd64/x86_64 ตาม TeamTalk SDK Linux ที่ทาง BearWare แจกสำหรับ Ubuntu 22 x86_64

## TeamTalk

โปรเจกต์เตรียม wrapper/native library สำหรับ TeamTalk SDK v5.22a และรองรับ `tcp_port`/`udp_port` แยกกัน โดย config เก่าที่มีเพียง `port` จะ migrate ไปทั้งสองค่าให้เอง

การตั้ง SDK license (ถ้ามี) จะทำก่อนสร้าง TeamTalk instance และไม่มีโค้ด bypass/trial patch อยู่ในโปรเจกต์

## ภาษาไทย

- ภาษาไทยอยู่ที่ `locales/th/LC_MESSAGES/messages.po`
- ไม่มี `msgstr` ว่างใน catalog ภาษาไทย ณ release นี้
- `locales/update_catalog.py` ใช้อัปเดตข้อความจาก source
- `locales/compile_locales.py` คอมไพล์ `.po` เป็น `.mo` ด้วย Python ล้วน ไม่ต้องติดตั้ง gettext/msgfmt
- ตัด `locales/po_translator.py` รุ่นเก่าที่พึ่ง `polib` และมีตัวอย่าง hard-coded ออก เพื่อไม่ทิ้ง dependency แฝงที่ไม่จำเป็น

## การตรวจ release

ผ่าน static validation ต่อไปนี้:

- Python source compile
- command registration ไม่มีชื่อซ้ำ
- help ครบทุก command และไม่มีรายการเก่าเกินจริง
- help syntax ทุกอันขึ้นต้น `/`
- `COMMANDS_TH.md` ตรงกับ command registry
- help ภาษาไทยแต่ละบรรทัดไม่เกิน 480 UTF-8 bytes
- ภาษาไทยไม่มีข้อความแปลว่าง
- ไม่มี multi-profile references
- shell scripts ผ่าน `bash -n`
- `docker-compose.yml` parse เป็น YAML ได้

ข้อจำกัดของสภาพแวดล้อมที่ใช้สร้าง release นี้: ไม่มี Docker daemon/CLI จึงยังไม่ได้ทำ live `docker build` และไม่มี TeamTalk native SDK ที่โหลดใช้งานได้ใน sandbox เพื่อทำการเชื่อมต่อ TeamTalk จริง การตรวจใน release จึงเป็น static/config/script validation และมี `tools/check_environment.py` สำหรับตรวจบนเครื่อง Linux ปลายทางอีกครั้ง


## Linux/Docker-only cleanup

- ตัด `bot/gui.py`, `requirements-gui.txt`, `setup.bat`, `run_bot.bat` ออก
- ลบเส้นทาง wxPython/GUI wizard จาก `bot/config_handler.py`
- setup/config ใช้ terminal และ `config.ini` เท่านั้น
