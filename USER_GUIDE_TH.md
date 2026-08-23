# คู่มือผู้ใช้ SNTalkBot

คำสั่งใช้ได้ทั้งในข้อความส่วนตัวและ Channel โดยไม่ต้องใส่ `/` เช่น `h`, `p เพลง`, `ap on`, `rs` และคำสั่งแบบเดิม `/h`, `/p เพลง`, `/ap on`, `/rs` ยังใช้ได้เหมือนเดิม เมื่อไม่ต้องการให้บอตอ่านหรือโต้ตอบกับข้อความใน Channel ผู้ดูแลใช้ `ci off` และเปิดกลับทาง Private ด้วย `ci on`


SNTalkBot เป็นบอต TeamTalk สำหรับเล่นสื่อและจัดการเซิร์ฟเวอร์ ทำงานบน Linux/Docker และเลือกโหมดได้ตามงาน

## โหมด

- **Full Bot** — Player + Server Manager
- **Player Bot** — เล่นเพลง คิว รายการโปรด TTS ประกาศเพลง และเครื่องมือ Player
- **Server Manager** — จัดการผู้ใช้ ห้อง ระบบ TTS และงานดูแลเซิร์ฟเวอร์ โดยไม่มีเครื่องเล่นเพลง

`h` (ย่อจาก `help`) แสดงเฉพาะคำสั่งที่มีจริงในโหมดนั้น และแต่ละคำสั่งส่งแยกหนึ่งข้อความเพื่อให้อ่านด้วย screen reader ง่าย

สถานะเริ่มต้นของบอตจะบอกประเภทให้เห็นทันที เช่น `Player Bot | พิมพ์ h เพื่อดูคำสั่ง`, `Server Manager Bot | พิมพ์ h เพื่อดูคำสั่ง` หรือ `Full Bot (Player + Server Manager) | พิมพ์ h เพื่อดูคำสั่ง` หากตั้งสถานะเองด้วย `cs <ข้อความ>` จะใช้ข้อความที่ตั้งไว้ และใช้ `cs auto` เพื่อกลับมาใช้สถานะตามประเภทบอต

## ควบคุมข้อความ Channel

มีสวิตช์ 2 ตัวที่ทำงานแยกกัน:

- `ci on|off|status` (`channelinput`) — ควบคุม **ข้อความที่เข้ามาจาก Channel** ถ้า `ci off` บอตจะไม่อ่าน ไม่ตอบคำสั่ง ไม่ทำ TTS/translation/selection หรือฟีเจอร์ข้อความใด ๆ จาก Channel แต่ Private ยังใช้ได้
- `cm on|off|status` — ควบคุม **ข้อความ Player ที่ส่งออกไป Channel** เช่น ใครเปิดเพลง ใครเพิ่มเพลงเข้าคิว หรือเปลี่ยนสถานะการเล่น ถ้า `cm off` ผู้ใช้ยังสั่งบอตได้ตามปกติ เพียงแต่ข้อความประกาศ Player จะไม่ไปรบกวนใน Channel

`ci` และ `cm` เป็นคำสั่งผู้ดูแล การปิด `ci` ไม่ได้ปิด `cm` และการปิด `cm` ไม่ได้ปิดการรับคำสั่งจาก Channel


## คำสั่งย่อ

คำสั่งหลักยังมีชื่อเดียว แต่คำสั่งย่อใช้พิมพ์แทนได้ เช่น:

```text
h  = help
rs = restart
sd = shutdown
w  = weather
wb = welcomebroadcast
ap = autoplay
ch = channel
pf = playfav
```

ดูคำสั่งย่อทั้งหมดได้จาก `h`/`help` หรือ `COMMANDS_TH.md`

## รายงานปัญหา

```text
dr <ข้อความ>
```

ส่งรายงานปัญหาโดยตรงถึงผู้พัฒนา SNTalkBot

`report <ข้อความ>` เป็นอีกคำสั่งหนึ่งสำหรับส่งข้อความหาแอดมิน TeamTalk ที่ออนไลน์ และมีเฉพาะ Manager/Full

## Player

รองรับ YouTube, YouTube Music, URL/stream, queue, favorites, history, seek, volume, speed, M1/M2/M3, autoplay, shuffle, cache/download และ TTS ประกาศเพลง/คิว

เสียง Google เป็นค่าเริ่มต้น และสามารถเปลี่ยนไปใช้เสียง Microsoft ได้

เสียงประกาศ Player พูดทีละข้อความ และไม่ลดหรือหยุดเสียงเพลงขณะประกาศ

## ใช้ TTUHelper

ติดตั้ง:

```bash
git clone https://github.com/nuttawat-arch/ttuhelper.git
cd ttuhelper
chmod +x install.sh ttuhelper.sh
sudo ./install.sh
sudo ttuhelper doctor
```

สร้างและเริ่มบอต:

```bash
sudo ttuhelper new
sudo ttuhelper run <ชื่อบอต>
```

คำสั่งที่ใช้บ่อย:

```text
ttuhelper logs <name>      ดูบันทึกแบบสด
ttuhelper restart <name>   รีสตาร์ตบอตหนึ่งตัว
ttuhelper stop <name>      หยุดบอต แต่เก็บข้อมูล
ttuhelper edit <name>      แก้ config.ini
ttuhelper ls               ดู instance และสถานะ
ttuhelper ps               ดู container ที่จัดการ
ttuhelper update           อัปเดตบอตที่กำลังรัน โดยรักษาข้อมูลเดิม
ttuhelper doctor           ตรวจระบบ Docker/helper
```

ดูรายละเอียดครบทุกคำสั่งใน `TTUHELPER_GUIDE_TH.md`

## ใช้ Docker โดยไม่ใช้ TTUHelper

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

ถ้ารันหลาย container ให้ใช้ชื่อ container, data directory และ `TTUTIL_PULSE_SINK` คนละชื่อ

## อัปเดต

ถ้าใช้ TTUHelper:

```bash
sudo ttuhelper update
```

ถ้าใช้ Docker เอง ให้ pull image ใหม่ ลบ container เดิม แล้วรัน `docker run` เดิมโดย mount data directory เดิม

## แหล่งทางการ

- SNTalkBot GitHub: https://github.com/nuttawat-arch/sntalkbot
- TTUHelper GitHub: https://github.com/nuttawat-arch/ttuhelper
- Docker Hub: https://hub.docker.com/r/nuttawat0295/sntalkbot
- Download: https://ttdl.nuttawat.ddnsfree.com
