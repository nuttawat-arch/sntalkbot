# คู่มือผู้ใช้ SNTalkBot

SNTalkBot เป็นบอต TeamTalk สำหรับ Linux/Docker ออกแบบให้ใช้งานได้ทั้งบอตเพลงและบอตจัดการเซิร์ฟเวอร์ โดยทุกคำสั่งใน TeamTalk ขึ้นต้นด้วย `/` และ `/help` จะส่งคำสั่งทีละข้อความเพื่ออ่านด้วยโปรแกรมอ่านหน้าจอได้ง่าย

## โหมดบอต

1. **Full Bot** — Player + Server Management ในตัวเดียว
2. **Player Bot** — เพลง คิว รายการโปรด YouTube/YouTube Music/URL และ TTS ประกาศเพลง โดยไม่รับหน้าที่จัดการผู้ใช้หรือเซิร์ฟเวอร์
3. **Server Manager** — จัดการ TeamTalk, TTS ข้อความ, ผู้ใช้, ห้อง, รายงาน, การแปล และเครื่องมือผู้ดูแล โดยไม่สร้าง Music Player

## ฟีเจอร์ Player

- ค้นหา YouTube และ YouTube Music
- เล่น URL และ stream โดยตรง
- คิว เปิด/ปิดคิว ดูคิว ลบรายการ สุ่มคิว และดูตำแหน่งคิว
- M1 Single, M2 Auto/Next, M3 Repeat
- Favorites, history, autoplay และเลือกผลค้นหา
- seek, pause/resume, next/previous, speed, volume
- bass, stereo/3D filters และ fade
- ดาวน์โหลดเสียงด้วย yt-dlp และอัปโหลดเข้า TeamTalk
- แคชสื่อและคำสั่งดู/ล้างแคช
- TTS ประกาศ “เพิ่มเข้าคิว”, “กำลังเล่น” และสถานะ Player
- Google standard gTTS เป็นค่าเริ่มต้น ไม่ต้องใช้ Google Cloud API key
- Microsoft Edge TTS ยังเลือกใช้ได้
- TTS ของ Player เป็น audio stream แยกจากเพลงและไม่ลดระดับเสียงเพลง
- TTS announcement ใช้ FIFO จึงพูดทีละข้อความ ไม่พูดซ้อนกันเอง

## ฟีเจอร์ Server Manager

- ดูผู้ใช้และแอดมินออนไลน์
- ประกาศข้อความ, สถานะบอต, ย้ายห้อง, ย้ายผู้ใช้
- kick/ban และ timed kick/ban
- jail/unjail
- ล็อกคำสั่งและบล็อกคำสั่งผู้ใช้ทั่วไป
- ระบบข้อความส่วนตัว/ข้อความออฟไลน์
- ห้องส่วนตัว 2 คน
- account request และสร้างบัญชีโดยผู้ดูแล
- translation และ whisper translation
- weather/location tools
- TTS สำหรับข้อความและคำสั่ง `/say`
- welcome และ welcome broadcast
- profanity filter, VPN/proxy detection และเครื่องมือดูแลอื่น ๆ

## รายงานถึงผู้พัฒนา

ทุกโหมดมี:

```text
/dr <ข้อความ>
```

คำสั่งนี้ส่งเฉพาะข้อมูลที่เกี่ยวข้องกับรายงานไปยังระบบทางการ:

`https://report.nuttawat.ddnsfree.com/api/report`

ข้อมูลประกอบมีเวอร์ชัน/โหมดบอต, TeamTalk server, bot nickname, nickname/username ของผู้รายงาน, channel และข้อความหลัง `/dr` เท่านั้น ไม่ส่ง password, channel password, cookies หรือบทสนทนาอื่น

`/report <ข้อความ>` เป็นคนละระบบและมีเฉพาะ Manager/Full โดยส่งรายงานหาแอดมิน TeamTalk ที่ออนไลน์

## วิธีแนะนำ: ใช้ TTUHelper

```bash
git clone https://github.com/nuttawat-arch/ttuhelper.git
cd ttuhelper
chmod +x install.sh ttuhelper.sh
sudo ./install.sh
sudo ttuhelper doctor
sudo ttuhelper new
sudo ttuhelper run <ชื่อบอต>
```

คำสั่งที่ใช้บ่อย:

```bash
sudo ttuhelper ls
sudo ttuhelper ps
sudo ttuhelper logs <ชื่อบอต>
sudo ttuhelper edit <ชื่อบอต>
sudo ttuhelper restart <ชื่อบอต>
sudo ttuhelper stop <ชื่อบอต>
sudo ttuhelper pull
sudo ttuhelper update
sudo ttuhelper doctor
```

แต่ละ instance มี `config.ini`, cookies, logs/cache/favorites และข้อมูลของตัวเองใต้ `/opt/sntalkbot-bots/<ชื่อบอต>/`

## ใช้ Docker image โดยไม่ใช้ TTUHelper

Pull image:

```bash
docker pull nuttawat0295/sntalkbot:latest
```

สร้าง data directory และ config เริ่มต้น:

```bash
sudo mkdir -p /opt/sntalkbot/mybot
sudo docker run --rm --entrypoint cat nuttawat0295/sntalkbot:latest /app/config_default.ini | sudo tee /opt/sntalkbot/mybot/config.ini >/dev/null
sudo touch /opt/sntalkbot/mybot/cookies.txt
sudo chown -R 10001:10001 /opt/sntalkbot/mybot
sudo chmod 750 /opt/sntalkbot/mybot
```

แก้ config:

```bash
sudo nano /opt/sntalkbot/mybot/config.ini
```

รัน:

```bash
docker run -d \
  --name sntalkbot-mybot \
  --network host \
  --restart unless-stopped \
  -v /opt/sntalkbot/mybot:/app/data \
  -e TTUTIL_CONFIG=/app/data/config.ini \
  -e TTUTIL_DATA_DIR=/app/data \
  -e TTUTIL_PULSE_SINK=ttu_mybot \
  -e TTUTIL_MPV_AO=pulse \
  nuttawat0295/sntalkbot:latest
```

ดู log:

```bash
docker logs -f sntalkbot-mybot
```

ถ้าสร้างหลาย container ต้องใช้ชื่อ container, data directory และ `TTUTIL_PULSE_SINK` คนละชื่อ

## อัปเดต

ถ้าใช้ TTUHelper:

```bash
sudo ttuhelper update
```

ถ้าใช้ Docker เอง:

```bash
docker pull nuttawat0295/sntalkbot:latest
docker rm -f sntalkbot-mybot
```

จากนั้นรัน `docker run` เดิมอีกครั้ง โดย mount data directory เดิมเพื่อรักษา config และข้อมูลถาวร

## แหล่งทางการ

- SNTalkBot GitHub: https://github.com/nuttawat-arch/sntalkbot
- TTUHelper GitHub: https://github.com/nuttawat-arch/ttuhelper
- Docker image: https://hub.docker.com/r/nuttawat0295/sntalkbot
- Download site: https://ttdl.nuttawat.ddnsfree.com
- Developer report service: https://report.nuttawat.ddnsfree.com

## รายการคำสั่งทั้งหมด

ดู `COMMANDS_TH.md` ซึ่งตรงกับคำสั่งที่ลงทะเบียนใน source และ `/help` ปัจจุบัน
