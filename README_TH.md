# SN TalkBot — Linux / Docker / TeamTalk Media Bot

โปรเจกต์นี้รวม `tt_utilities-nut`, ส่วนที่จำเป็นจาก `tt_utilities-main` และแนวทางที่แข็งแรงจาก `TTMediaBot-th` ไว้ในบอต TeamTalk ตัวเดียว โดยใช้ single-bot config เท่านั้น ไม่มีระบบหลายโปรไฟล์

## จุดสำคัญของรุ่นนี้

- คำสั่งผู้ใช้ทั้งหมดต้องขึ้นต้นด้วย `/`; ข้อความธรรมดาจะไม่ถูก parser ตีความเป็นคำสั่ง
- ชื่อคำสั่งที่ลงทะเบียนจริงไม่ซ้ำกัน และระบบจะหยุดทันทีด้วย error หากนักพัฒนาเพิ่มชื่อซ้ำในอนาคต
- `/help` ส่งหัวข้อก่อนหนึ่งข้อความ แล้วส่งคำสั่งพร้อมคำอธิบายทีละคำสั่ง หนึ่งคำสั่งต่อหนึ่ง TeamTalk private message
- Player ใช้ `yt-dlp` โดยตรง รองรับ YouTube, YouTube Music, URL/stream, playlist/channel, queue, favorites, autoplay, history, seek, volume/speed, M1/M2/M3, audio filters และ download
- มี worker prefetch ลิงก์ล่วงหน้าเพื่อไม่ให้การ extract ของ yt-dlp ไปบล็อก TeamTalk event thread
- มี TTS ประกาศเพลงและคิว พร้อมลดระดับเพลงชั่วคราวระหว่างประกาศ
- รองรับการ block command เป็นรายคำสั่งด้วย `/blockcmd`
- reconnect ทำใน worker แยกและกำหนดจำนวนครั้ง/ช่วงเวลาได้
- Linux headless ใช้ MPV + PulseAudio virtual sink เพื่อส่งเสียงจริงเข้า TeamTalk
- รองรับ Docker และ systemd
- ภาษาไทยอยู่ใน `locales/th/LC_MESSAGES/` และ catalog ปัจจุบันไม่มีข้อความไทยว่าง
- config เดียว ใช้ `config.ini`; config เก่าที่มี `[server] port=` จะถูก migrate เป็น `tcp_port`/`udp_port` อัตโนมัติ
- ระบบต้อนรับแยกเป็น 2 ส่วน: ประกาศต้อนรับสุ่มตอนล็อกอิน (`welcome_broadcast`) และข้อความคงที่ตอนเข้าห้อง (`welcome_mode`) เปิด/ปิดแยกกันได้


## ระบบข้อความต้อนรับและ Welcome Broadcast

ระบบต้อนรับมี 2 แบบและควบคุมแยกกัน:

1. **Random Welcome Broadcast ตอนผู้ใช้ล็อกอินเข้าเซิร์ฟเวอร์**
   - เปิดจาก TeamTalk: `/welcomebroadcast on`
   - ปิดจาก TeamTalk: `/welcomebroadcast off`
   - ดูสถานะ: `/welcomebroadcast status`
   - ส่ง `/welcomebroadcast` โดยไม่ใส่อาร์กิวเมนต์เพื่อสลับเปิด/ปิดทันที
   - คำสั่งจะบันทึกค่ากลับ `config.ini` จึงยังคงสถานะเดิมหลังรีสตาร์ตบอต
   - แก้ไฟล์โดยตรงได้ที่ `[bot] welcome_broadcast = True` หรือ `False` แล้วรีสตาร์ตบอต
   - ภาษาไทยมีข้อความต้อนรับสุ่ม 94 รูปแบบ เท่ากับชุดข้อความสุ่มภาษาอังกฤษของระบบปัจจุบัน และรองรับ `{nickname}` / `{country}`

2. **Static Welcome ตอนผู้ใช้เข้าห้องที่บอตอยู่**
   - ใช้ `/welcome` เพื่อสลับเปิด/ปิด
   - ตั้งใน config ด้วย `[bot] welcome_mode = 1` เพื่อเปิด หรือ `0` เพื่อปิด
   - แก้ข้อความได้ที่ `[bot] welcome_msg` โดยคำว่า `ชื่อ` จะถูกแทนด้วย nickname ของผู้ใช้

การปิด `welcome_broadcast` จะไม่ปิดข้อความต้อนรับแบบ `welcome_mode` และการปิด `/welcome` ก็จะไม่ปิด Random Welcome Broadcast

## ติดตั้งแบบ Native บน Ubuntu/Debian x86_64 — คำสั่งเดียว

หลังแตกไฟล์และ `cd` เข้ามาในโฟลเดอร์โปรเจกต์แล้ว ให้รัน **คำสั่งเดียวนี้**:

```bash
./install.sh
```

`install.sh` จะทำให้ครบโดยอัตโนมัติ: ติดตั้งแพ็กเกจระบบที่จำเป็น, สร้าง `.venv`, ติดตั้ง Python dependencies, ติดตั้ง Deno สำหรับ yt-dlp EJS, ดาวน์โหลด TeamTalk SDK runtime ทางการ, คอมไพล์ภาษา และรัน environment/project validation จากนั้นจะสร้าง `config.ini` จาก template เฉพาะเมื่อยังไม่มีไฟล์นี้อยู่ จึงรันซ้ำหลังอัปเดตได้โดยไม่ทับ config เดิม

เมื่อติดตั้งเสร็จ ให้แก้ `config.ini` โดยอย่างน้อยตั้ง `[server] address`, `tcp_port`, `udp_port`, `username`, `password` และ `[bot] default_channel` แล้วรัน:

```bash
./run_linux.sh
```

หากต้องการจัด audio routing เองให้ใช้:

```bash
TTUTIL_AUTO_PULSE=0 ./run_linux.sh
```

ดูอุปกรณ์ที่ TeamTalk/MPV มองเห็น:

```bash
.venv/bin/python main.py --devices
```

สำหรับ Linux headless แนะนำ `input_device = auto` และ `output_device = auto` เพราะ launcher ตั้ง default PulseAudio sink/source ให้แล้ว

## วิธีทำให้รันด้วย systemd

ตัวอย่าง service อยู่ที่ `sntalkbot.service` โดยสมมติว่าโปรเจกต์อยู่ `/opt/sntalkbot` และรันด้วย user `sntalkbot`

```bash
sudo useradd --system --home /opt/sntalkbot --shell /usr/sbin/nologin sntalkbot 2>/dev/null || true
sudo chown -R sntalkbot:sntalkbot /opt/sntalkbot
sudo cp sntalkbot.service /etc/systemd/system/sntalkbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now sntalkbot
sudo systemctl status sntalkbot
```

ดู log:

```bash
journalctl -u sntalkbot -f
```

## Build และ Push ขึ้น Docker Hub

ค่าเริ่มต้นของแพ็กนี้ใช้ repository เดิมของ helper คือ `nuttawat0295/sntalkbot:latest` เพื่อให้ฝั่ง Server Helper ใช้งานต่อได้ทันที

ล็อกอิน Docker Hub ครั้งแรก:

```bash
docker login
```

จากนั้น build + push ใช้คำสั่งเดียว:

```bash
./publish.sh
```

ถ้าต้องการ repository/tag อื่น:

```bash
TTU_IMAGE_REPO=ชื่อผู้ใช้/ชื่อรีโป TTU_TAG=เวอร์ชัน ./publish.sh
```

Server Helper รองรับการเปลี่ยน repository/tag โดยแก้ `/etc/default/ttuhelper` หรือกำหนด environment `TTU_IMAGE_REPO` และ `TTU_TAG`

## Docker

Docker image นี้ตั้งใจสำหรับ `linux/amd64` เพราะ TeamTalk SDK v5.22a Ubuntu runtime ที่ใช้อยู่เป็น x86_64

สร้างและรัน:

```bash
docker compose up -d --build
```

ครั้งแรก `docker-entrypoint.sh` จะสร้าง `./data/config.ini` จาก `config_default.ini` ให้ แก้ไฟล์นั้นแล้ว restart:

```bash
docker compose restart
```

ดู log:

```bash
docker compose logs -f
```

หยุด:

```bash
docker compose down
```

โฟลเดอร์ `./data` เก็บ config, favorites และ error log แบบ persistent จึงไม่หายเมื่อสร้าง container ใหม่

ไม่ต้องเปิด inbound port สำหรับ bot เพราะ bot เป็นฝ่ายเชื่อมต่อออกไปยัง TeamTalk server

## ระบบเสียงบน Linux/Docker

โปรเจกต์ไม่ได้ใช้ `ao=null` สำหรับเสียง เพราะโหมดนั้นไม่มี audio output ให้ TeamTalk จับ เส้นทางที่ใช้คือ:

```text
MPV (ao=pulse)
 -> PulseAudio null sink: sntalkbot (หรือชื่อ instance ที่ TTUHelper กำหนด)
 -> monitor source: sntalkbot.monitor
 -> TeamTalk input device
 -> Voice Transmission
```

`run_linux.sh` และ Docker ตั้ง `TTUTIL_MPV_AO=pulse` และใช้ `tools/setup_pulse_bridge.sh` เพื่อให้ MPV กับ TeamTalk อยู่บน PulseAudio runtime เดียวกัน

## Config สำคัญ

ตัวอย่างเต็มอยู่ใน `config_default.ini`

```ini
[server]
address = your-teamtalk-host
tcp_port = 10333
udp_port = 10333
encrypted = False
username = bot
password = secret

[bot]
language = th
default_channel = /
blocked_commands =
reconnection_attempts = -1
reconnection_timeout = 10

[playback]
input_device = auto
output_device = auto
queue_mode = True
play_mode = 2
autoplay_enabled = True
announce_tracks = True
announce_queue = True
announcement_provider = gtts
announcement_tts_mode = google
announcement_microsoft_voice = th-TH-PremwadeeNeural
announcement_google_lang = th
announcement_google_tld = com
announcement_google_slow = False
announcement_rate = 0
announcement_google_speed = 1.0

[tts]
provider = gtts
mode = google
google_lang = th
google_tld = com
google_slow = False
google_speed = 1.0

[telegram]
telegram_bot_token =
report_chat_id =
```

`reconnection_attempts = -1` หมายถึงพยายามเชื่อมต่อใหม่ต่อเนื่อง ส่วนค่าตั้งแต่ `0` ขึ้นไปเป็นจำนวนครั้งสูงสุด

## Logging

บอตเขียน log แบบ rotating ไว้ที่ `TTUTIL_DATA_DIR/sntalkbot.log` ค่าเริ่มต้นคือ 5 MiB ต่อไฟล์ เก็บ backup 3 ไฟล์ และแสดง INFO ทาง console ด้วย ปรับได้ใน `config.ini`:

```ini
[logging]
level = INFO
max_bytes = 5242880
backup_count = 3
console = True
```

คำสั่ง `/clearlog` จะล้างไฟล์ log ปัจจุบันที่ตำแหน่งเดียวกัน

## คำสั่ง

รายการทั้งหมดอยู่ใน `COMMANDS_TH.md` และตรงกับ registry ของ source ปัจจุบัน

ใน TeamTalk:

```text
/help
```

จะส่งคำสั่งทุกตัวแยกข้อความ เช่น:

```text
/p <query> : ค้นหาและเล่นหรือเพิ่มเพลงจาก YouTube ลงคิว
/pm <query> : ค้นหาและเล่นหรือเพิ่มเพลงจาก YouTube Music ลงคิว
/ql : แสดงรายการในคิวปัจจุบัน
```

ดูคำสั่งเดียว:

```text
/help p
```

## ภาษาไทย

source translation:

```text
locales/th/LC_MESSAGES/messages.po
```

ไฟล์ที่โปรแกรมใช้จริง:

```text
locales/th/LC_MESSAGES/messages.mo
```

หลังแก้ source และมีข้อความใหม่ ให้ update catalog ภาษาไทย:

```bash
python locales/update_catalog.py --locale th
```

จากนั้นแปล `msgstr` ที่ยังว่างในไฟล์ `.po` แล้วคอมไพล์:

```bash
python locales/compile_locales.py
```

เครื่องมือ compile เป็น Python ล้วน ไม่บังคับติดตั้ง `gettext` หรือ `msgfmt`

## yt-dlp / YouTube / YouTube Music

requirements ล็อก `yt-dlp[default,curl-cffi]==2026.8.19` และใช้ Python API โดยตรง ไม่ใช้ `py-yt-search` อีกชั้น

YouTube รุ่นปัจจุบันใช้ EJS challenge solver และ JavaScript runtime; โปรเจกต์ติดตั้ง `yt-dlp-ejs` ผ่าน `default` dependency group และ Docker ติดตั้ง Deno 2.9.5 ให้แล้ว

Native server ต้องมี Deno ใน PATH ตรวจด้วย:

```bash
deno --version
```

หาก YouTube เปลี่ยนและ stable มีปัญหา ให้ตรวจเอกสาร yt-dlp ก่อนอัปเดต ไม่ควรแก้ extractor แบบ hard-code ในบอต

## TeamTalk SDK และ License

`tools/download_teamtalk_sdk.py` ดาวน์โหลด TeamTalk SDK Standard v5.22a จาก BearWare โดยตรง แล้วนำ `TeamTalk5.py` และ `libTeamTalk5.so` มาไว้ใน root

```bash
python tools/download_teamtalk_sdk.py
```

หากมี SDK license ให้ใส่:

```ini
[teamtalk_license]
license_name =
license_key =
```

ถ้าปล่อยว่าง โปรแกรมไม่ปลอม license และไม่ bypass trial ข้อกำหนดทางการของ BearWare ระบุว่า SDK binary เป็น trial 30 วันและจะ disable ตัวเองหลังช่วงดังกล่าวสำหรับการใช้แบบ end-user application ดังนั้นสิ่งที่ได้ยินว่าใช้ SDK binary ต่อได้ถาวรโดยไม่ซื้อ license ไม่ตรงกับเอกสารทางการ v5.22a

รายละเอียด dependency และแหล่งดาวน์โหลดทั้งหมดอยู่ใน `DEPENDENCIES_TH.md`

## สิ่งที่นำจาก TTMediaBot-th มาเสริม

นำแนวคิดที่เหมาะกับโปรเจกต์นี้มาใช้ ได้แก่ worker prefetch, PulseAudio virtual sink สำหรับ server/container, per-command block list, reconnect configuration, channel ID helper และแนวคิดการเลือกผลลัพธ์จากรายการ

ไม่ได้ยก service VK/Yandex Music เข้ามาแบบตรง ๆ เพราะต้องพึ่ง token/auth และ dependency เฉพาะบริการ และไม่ได้อยู่ในเป้าหมาย YouTube/YouTube Music ที่กำหนดไว้ การเพิ่มโดยเปิดค่าเริ่มต้นจะทำให้ production bot มี failure surface มากขึ้นโดยไม่จำเป็น

ไม่ได้ยก dynamic Python event-handler loader ที่เปิดให้โหลดโค้ดภายนอกมาใช้ เพราะเป็น arbitrary-code execution surface บนบอตหลักและไม่จำเป็นต่อความสามารถที่ขอ

## ตรวจ release ก่อนใช้งานจริง

```bash
python tools/validate_project.py
python tools/check_environment.py
bash -n run_linux.sh docker-entrypoint.sh tools/setup_pulse_bridge.sh setup.sh
```

`validate_project.py` ต้องรายงานว่าไม่มี duplicate commands, help ครบทุก command, ทุก help syntax ขึ้นต้น `/`, ภาษาไทยไม่มีข้อความว่าง และไม่มีระบบ multi-profile หลงเหลือ


## โหมดบอต (Full / Player / Server Manager)

ตั้งแต่รุ่นนี้เป็นต้นไป ตัวบอตรองรับสวิตช์ระดับฟีเจอร์ผ่าน `[features]` ใน `config.ini`:

```ini
[features]
player_enabled = True
server_management_enabled = True
```

ชุดค่ามาตรฐานที่ใช้งานบ่อย:

```text
Full Bot       -> player_enabled=True  / server_management_enabled=True
Player Bot     -> player_enabled=True  / server_management_enabled=False
Server Manager -> player_enabled=False / server_management_enabled=True
```

ผลลัพธ์เชิงพฤติกรรม:

- Full Bot: โหลดครบทั้งระบบเล่นเพลงและระบบจัดการเซิร์ฟเวอร์
- Player Bot: ไม่โหลดโมดูลจัดการเซิร์ฟเวอร์หลัก จึงเหลือเฉพาะคำสั่งเล่นเพลงและคำสั่งทั่วไป
- Server Manager: ไม่สร้าง Music Player/queue/prefetch จึงไม่มีคำสั่งเล่นเพลง; TTS ของระบบอาจยังใช้ libmpv สำหรับเสียงพูด

หลังแก้ `[features]` แล้ว ให้ restart process หรือ recreate container เพื่อให้โหมดใหม่มีผล


## ตัวอย่างเวิร์กโฟลว์การปล่อย image

### 1) เตรียมและ publish image

```bash
./install.sh
docker login
./publish.sh
```

หรือระบุ tag เอง:

```bash
TTU_IMAGE_REPO=nuttawat0295/sntalkbot TTU_TAG=2026.08.23-r5 ./publish.sh
```

### 2) บนเซิร์ฟเวอร์ที่ใช้ helper

```bash
sudo ttuhelper doctor
sudo ttuhelper pull
sudo ttuhelper new
sudo ttuhelper run <ชื่อบอต>
```

### 3) เมื่อต้องการอัปเดต image

```bash
./publish.sh
# ฝั่งเซิร์ฟเวอร์
sudo ttuhelper update
```

### 4) เมื่อต้องการย้อนกลับ image

helper จะอิงจาก `TTU_IMAGE_REPO` และ `TTU_TAG` ใน `/etc/default/ttuhelper` ดังนั้นให้เปลี่ยน tag ไปเป็นรุ่นก่อน แล้วสั่ง:

```bash
sudo ttuhelper update
```

ถ้าต้องการทดสอบ image ใหม่โดยไม่ทับ `latest` แนะนำให้ push เป็น tag ใหม่ก่อน เช่น `2026.08.23-r5` แล้วค่อยสลับ tag ที่ helper ใช้


## การแบ่งหน้าที่ Full / Player / Server Manager

Runtime `/help` แสดงเฉพาะคำสั่งที่ถูก register ในโหมดนั้นจริง ไม่ได้เอาคำสั่งทุกโมดูลมาปนกัน:

- **Player Bot**: Player/queue + คำสั่งทั่วไปที่ปลอดภัย + `/dr`; ไม่มี AdminCog, UserManager, Account Request, Translator หรือคำสั่ง TTS ของ Server Manager
- **Server Manager**: คำสั่งจัดการเซิร์ฟเวอร์ + TTS แบบเดิม (`/say`, `/tts`, `/ttsmode`, `/voice`, `/get_voices` ฯลฯ); ไม่มี Music Player/queue
- **Full Bot**: รวมทั้งสองชุด โดย Player TTS ใช้ชื่อคำสั่ง `p...` แยกจาก Manager TTS จึงไม่ชนกัน

`/report <message>` เป็นรายงานไปยังแอดมิน TeamTalk และมีเฉพาะ Manager/Full ส่วน `/dr <message>` ส่งตรงถึงระบบรายงานผู้พัฒนา SNTalkBot ทางการและมีทุกโหมด

Alias ซ้ำที่เลิกใช้แล้ว: `/h`, `/gl`, `/rs`, `/sd` เหลือคำสั่งหลัก `/help`, `/l`, `/restart`, `/shutdown` อย่างละตัว

## Player TTS — ประกาศคิว/เพลงแบบไม่พูดซ้อน

รุ่น `2026.08.23-r5` เปลี่ยน Player announcement จากการยิงหลาย thread พร้อมกันเป็น **FIFO queue + worker เดียว** ดังนั้นข้อความเช่น “เพิ่มเพลงเข้าคิวแล้ว” และ “กำลังเล่นเพลง...” จะรอพูดต่อกันตามลำดับ ไม่พูดทับกัน

คำสั่ง Player TTS:

```text
/ptts status
/ptts on
/ptts off
/ptts tracks on|off
/ptts queue on|off
/pttsmode microsoft|google
/pvoices [langcode]
/pvoice <voice_or_language>
/pttsrate <-100..100>
/pttsspeed <0.25..4.0>
```

`/ptts`, `/pttsmode`, `/pvoice`, `/pttsrate`, `/pttsspeed` เป็นคำสั่งผู้ดูแลเพราะเปลี่ยนค่ารวมของ Player; `/pvoices` เป็นคำสั่งอ่านอย่างเดียว

### Google Standard TTS (gTTS) — ค่าเริ่มต้นของ Player และ Server Manager

โหมด `google` ใช้ `gTTS` หรือ Google Translate TTS แบบมาตรฐาน ไม่ใช่ Google Cloud Text-to-Speech จึงไม่ต้องมี API key, service account หรือ billing

ค่าเริ่มต้นภาษาไทย:

```ini
[tts]
provider = gtts
mode = google
google_lang = th
google_tld = com
google_slow = False
google_speed = 1.0
```

Player ใช้:

```text
/pttsmode google
/pvoices th
/pvoice th
/pttsspeed 1.0
```

ใน Google mode คำสั่ง `/pvoice` ใช้เลือก **รหัสภาษา** เช่น `th`, `en`, `ja` เพราะ gTTS ไม่มีรายชื่อ named voice แบบ Google Cloud

Server Manager ใช้:

```text
/ttsmode google
/get_voices th
/voice th
/speed 1.0
/say ข้อความทดสอบ
```

ใน Google mode คำสั่ง `/voice` ก็ใช้รหัสภาษาเช่นเดียวกัน และ `/ld` ยังใช้เปิด/ปิดการตรวจจับภาษาอัตโนมัติได้

Microsoft Edge TTS ยังเก็บไว้เป็นตัวเลือกสำรอง:

```text
/pttsmode microsoft
/pvoices th-TH
/pvoice th-TH-PremwadeeNeural
/pttsrate 0

/ttsmode microsoft
/get_voices th-TH
/voice th-TH-PremwadeeNeural
/rate 0
```

เมื่ออัปเดตจาก r2 หรือต่ำกว่า ระบบจะ migrate ค่า TTS ครั้งเดียว: เอา key ของ Google Cloud เก่าออกและตั้ง Google standard gTTS เป็นค่าเริ่มต้น หลังจาก migration แล้วถ้าผู้ดูแลสลับกลับ Microsoft ระบบจะไม่บังคับกลับ Google ใน restart ถัดไป

## `/dr` — รายงานถึงผู้พัฒนา SNTalkBot โดยตรง

`/dr <message>` ใช้ endpoint ทางการที่ฝังใน SNTalkBot: `https://report.nuttawat.ddnsfree.com/api/report` ผู้ใช้ไม่ต้องตั้ง Telegram token หรือ chat ID ใน container

ข้อมูลที่ส่งเมื่อผู้ใช้เรียก `/dr` เท่านั้น: เวอร์ชัน/โหมดบอต, ชื่อ TeamTalk server และ host/port, ชื่อบอต, nickname/username ของผู้รายงาน, channel และข้อความที่ผู้ใช้พิมพ์หลัง `/dr` ระบบไม่ส่ง TeamTalk password, channel password, cookies หรือบทสนทนาอื่น

หาก API กลางหยุดทำงาน บอตจะแจ้งว่าระบบรายงานขัดข้องชั่วคราวและจะไม่ทำให้บอต crash ส่วน `/report` ยังคงเป็นคำสั่งรายงานหาแอดมิน TeamTalk ตามเดิม

## อัปเดต Docker image และ instance เดิม

หลังแก้ source และ push GitHub แล้ว ให้ build/push tag ใหม่ เช่น:

```powershell
docker build --platform linux/amd64 -t nuttawat0295/sntalkbot:2026.08.23-r5 .
docker push nuttawat0295/sntalkbot:2026.08.23-r5
docker tag nuttawat0295/sntalkbot:2026.08.23-r5 nuttawat0295/sntalkbot:latest
docker push nuttawat0295/sntalkbot:latest
```

บน server ถ้าใช้ `latest`:

```bash
sudo ttuhelper update
```

คำสั่งนี้ pull image ใหม่และ recreate **เฉพาะ instance ที่กำลังรันอยู่** โดยเก็บ `/opt/sntalkbot-bots/<name>/config.ini`, cookies, favorites, cache และข้อมูล persistent เดิมไว้

## Player TTS และเพลง

Player announcement ใช้ audio stream แยกจากเพลงและ mix กันที่ PulseAudio โดย **ไม่ลด volume, ไม่ pause และไม่ duck เพลง** ขณะพูด TTS ส่วน FIFO queue ทำให้ข้อความ TTS พูดทีละข้อความไม่ซ้อนกันเอง

## 2026.08.23-r5

- `/dr` ใช้ official developer relay ที่ `https://report.nuttawat.ddnsfree.com/api/report`
- Telegram Bot Token ไม่อยู่ใน Docker image หรือ config ของผู้ใช้
- Player TTS และเพลงยังเป็น audio stream แยก ไม่มี music ducking
