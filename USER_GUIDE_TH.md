# คู่มือผู้ใช้ SNTalkBot

ทั้งข้อความส่วนตัวและ Channel/Broadcast ใช้คำสั่งแบบไม่ต้องใส่ `/` เหมือนกัน เช่น `h`, `p เพลง`, `ap on`, `rs` เครื่องหมาย `/` ยังใช้ได้เพื่อ compatibility แต่ไม่จำเป็น หากไม่ต้องการให้บอตตอบสนองต่อ command/TTS/Player/translation ใน Channel ให้ใช้ `ci off` และเปิดกลับด้วย `ci on`; moderation ที่เปิดด้วย `filter on` ยังทำงานกับข้อความที่บอตได้รับ


SNTalkBot เป็นบอต TeamTalk สำหรับเล่นสื่อและจัดการเซิร์ฟเวอร์ ทำงานบน Linux/Docker และเลือกโหมดได้ตามงาน

## โหมด

- **Full Bot** — Player + Server Manager
- **Player Bot** — เล่นเพลง คิว รายการโปรด TTS ประกาศเพลง และเครื่องมือ Player
- **Server Manager** — จัดการผู้ใช้ ห้อง ระบบ TTS และงานดูแลเซิร์ฟเวอร์ โดยไม่มีเครื่องเล่นเพลง

ทั้งสามประเภทแยกหน้าที่จริงใน runtime ไม่ใช่แค่ชื่อ: Player Bot = Common + Player เท่านั้น, Server Manager = Common + Manager เท่านั้น และ Full Bot = Common + Player + Manager จึงไม่ดึงคำสั่งข้ามฝ่ายมาปนกัน

ถ้าส่งข้อความที่ไม่ตรงกับคำสั่งหรือ workflow ของโหมดนั้น บอตจะตอบกลับทางข้อความส่วนตัวว่าไม่รู้จักคำสั่งหรือคำสั่งไม่ถูกต้อง และบอกให้พิมพ์ `h` เพื่อดูวิธีใช้ โดยไม่ตอบกับ event ภายในอย่างสถานะ `typing`

`h` (ย่อจาก `help`) ใช้เหมือนกันทั้ง Private และ Channel/Broadcast โดยไม่ต้องใส่ `/` และจะแสดงเฉพาะคำสั่งที่มีจริงในโหมดนั้น แต่ละคำสั่งส่งแยกหนึ่งข้อความเพื่อให้อ่านด้วย screen reader ง่าย

สถานะเริ่มต้นของบอตจะบอกประเภทและคำสั่ง help แบบสั้นทันที เช่น `Player Bot | พิมพ์ h เพื่อดูวิธีใช้`, `Server Manager Bot | พิมพ์ h เพื่อดูวิธีใช้` หรือ `Full Bot (Player + Server Manager) | พิมพ์ h เพื่อดูวิธีใช้` หากตั้งสถานะเองด้วย `cs <ข้อความ>` จะใช้ข้อความที่ตั้งไว้ และใช้ `cs auto` เพื่อกลับมาใช้สถานะตามประเภทบอต

## Dashboard และเหตุการณ์ TeamTalk

`status` ใช้ได้ทุกประเภทบอตและส่งผลทาง Private เป็นหลายบรรทัดสั้นเพื่อให้ screen reader อ่านง่าย โดยข้อมูลจะไม่ปนข้ามหน้าที่:

- ทุกโหมด: ประเภทบอต, uptime, ห้องปัจจุบัน, จำนวนคนในห้องปัจจุบันและจำนวนผู้ใช้ทั้งเซิร์ฟเวอร์แยกกัน รวม Voice/Media/Video/Desktop ของห้องและทั้งเซิร์ฟเวอร์
- Player/Full: เพลงปัจจุบัน, จำนวนคิว, Queue Mode, M1/M2/M3, Autoplay และแหล่ง Cookies ที่กำลังใช้
- Manager/Full สำหรับผู้ดูแล: สถานะ `filter`, `ci`, `ic`, command lock และ welcome

`events [1-25]` มีเฉพาะ **Manager/Full และผู้ดูแล** ใช้ดูเหตุการณ์ล่าสุด เช่น login/join/leave, เปลี่ยนชื่อหรือ status, สร้าง/แก้/ลบ Channel, เพิ่ม/ลบไฟล์ใน Channel, server settings update และการเริ่ม/หยุด media/video/desktop เหตุการณ์เก็บในหน่วยความจำสูงสุดแบบวงแหวนและหายเมื่อบอตรีสตาร์ต จึงไม่เพิ่มฐานข้อมูลหรือไฟล์ log ถาวรอีกชุด

เมื่อผู้ดูแลใช้คำสั่ง Manager/Full ระบบจะบันทึกเฉพาะว่า **ใครใช้คำสั่งหลักอะไร** โดยไม่เก็บ argument ของคำสั่ง ดังนั้นรหัสผ่านจากการสร้างบัญชี ข้อความส่วนตัว token หรือค่า secret จะไม่ถูกใส่ใน `events` การเริ่ม/หยุดพูดของผู้ใช้ยังแสดงเป็นจำนวนสดใน `status` แต่ไม่ถูกเขียนทุกครั้งลง `events` เพื่อไม่ให้รายการเต็มด้วยกิจกรรมเสียงปกติ

## ควบคุมข้อความ Channel

มีสวิตช์ 3 ตัวที่ทำงานแยกกัน:

- `ic on|off|status` (`intercept`, Manager/Full) — ควบคุม **การดักข้อความจากผู้ใช้ในทุก Channel ของเซิร์ฟเวอร์** เมื่อเปิด บอตสามารถตรวจ moderation/คำหยาบในห้องที่ตัวบอตไม่ได้อยู่ด้วย เมื่อปิด บอตจะยังเห็น Channel ที่ตัวเองอยู่ตามปกติ แต่จะไม่ดักห้องอื่น
- `ci on|off|status` (`channelinput`) — ควบคุม **การตอบสนองปกติต่อ Channel** เช่น command, TTS, Player, translation และ selection ถ้า `ci off` สิ่งเหล่านี้จะไม่ตอบสนองต่อ Channel แต่ **moderation/กรองคำหยาบยังตรวจข้อความที่บอตได้รับอยู่** และ Private ยังใช้ได้
- `cm on|off|status` — ควบคุม **ข้อความ Player ที่ส่งออกไป Channel** เช่น ใครเปิดเพลง ใครเพิ่มเพลงเข้าคิว หรือเปลี่ยนสถานะการเล่น ถ้า `cm off` ผู้ใช้ยังสั่งบอตได้ตามปกติ เพียงแต่ข้อความประกาศ Player จะไม่ไปรบกวนใน Channel

ถ้าต้องการให้บอตเฝ้าคำหยาบทั่วเซิร์ฟเวอร์ แต่ไม่ตอบคำสั่งใน Channel ให้ใช้ `ic on`, `filter on`, `ci off` ไม่ว่าจะส่งจาก Private หรือ Channel ก็ใช้รูปแบบเดียวกัน

`ic`, `ci` และ `cm` เป็นสวิตช์คนละหน้าที่ การปิด `ci` **ไม่ปิด moderation** และไม่เปลี่ยนค่า `ic` หรือ `cm`


## กรองคำทุกภาษา

`filter on|off|status` (`ft`) เป็น master switch ของระบบกรองคำทั้งหมด Runtime ใช้ `blacklist.txt` เป็นรายการ canonical เพียงชุดเดียว ซึ่งรวมภาษาอังกฤษ ภาษาอาหรับ ภาษาไทย และรายการเดิมอื่น ๆ ไว้ฝ่ายเดียวกันแล้ว การพบคำใช้ `blacklist_mode` ของ Manager คือ Kick หรือ Ban ตาม config; `badword.txt` ยังคงอยู่ในแพ็กเกจเพื่อ compatibility/reference และ validator บังคับว่าทุกคำในไฟล์นี้ต้องมีอยู่ใน `blacklist.txt` ด้วย จึงไม่มีเส้นทางลงโทษแยกกันอีก

ตัว matcher รองรับคำไทยรูปติดกันและการเว้นอักขระ เช่น `ค ว ย` พร้อมป้องกัน false positive ของคำสั้น เช่น `หี` ไม่จับ `หีบ`; ฝั่งภาษาอังกฤษใช้ขอบเขตคำ จึงไม่เอา `ass` ไปจับคำปกติอย่าง `class` หรือ `password`

`filter off` ปิดการกรองทุกภาษาพร้อมกัน รวมข้อความ ชื่อผู้ใช้ และชื่อ/หัวข้อ Channel; `filter on` เปิดทั้งหมด ตัวกรองทำงานก่อน `ci` ดังนั้น `ci off` ไม่ทำให้การกรองที่เปิดอยู่หยุด หากต้องการตรวจห้องอื่นที่บอตไม่ได้อยู่ด้วยให้คง `ic on` นอกจากนี้เมื่อผู้ใช้เปลี่ยน nickname/status หลัง login หรือมีการแก้ชื่อ/Topic Channel หลังสร้างแล้ว ระบบจะตรวจซ้ำจาก TeamTalk update event ทันที จึงไม่สามารถหลบ filter ด้วยการเปลี่ยนข้อมูลภายหลังได้

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

คำสั่งย่อถูกจัดให้หนึ่งคำสั่งหลักมี shorthand เดียว: Common ใช้ `a = about`; Player/Full ใช้ `gl = l`, `c = select`, `sb = -`, `sf = +`; Manager/Full ใช้ `j = join`, `sc = save`, `vt = voicetx` ส่วน alias ซ้ำหรือชนความหมายใหม่จะไม่ถูกย้อนกลับมา

## รายงานปัญหา

```text
dr <ข้อความ>
```

ส่งรายงานปัญหาโดยตรงถึงผู้พัฒนา SNTalkBot

`report <ข้อความ>` เป็นอีกคำสั่งหนึ่งสำหรับส่งข้อความหาแอดมิน TeamTalk ที่ออนไลน์ และมีเฉพาะ Manager/Full

## Player

รองรับ YouTube, YouTube Music, URL/stream, playlist, channel, queue, favorites, history, seek, volume, speed, M1/M2/M3, autoplay, shuffle, cache/download และ TTS ประกาศเพลง/คิว

### Playlist และ playlist ต่อเนื่อง

- `u <ลิงก์>` ใช้เปิด URL หรือเริ่ม playlist แรกตามพฤติกรรมเดิม
- `pp <ลิงก์ playlist>` ใช้ต่อ playlist ชุดที่ 2, 3, 4 ... โดยไม่หยุดเพลงปัจจุบันในโหมดปกติ
- รองรับทั้ง `youtube.com` และ `music.youtube.com` playlist
- playlist ที่ต่อด้วย `pp` จะเรียงต่อท้ายตามลำดับที่เจ้าของ playlist จัดไว้
- ใช้ `c <ลำดับ>` เพื่อกระโดดไปตำแหน่งที่ต้องการใน playlist/session แบบสั้น เช่น `c 56`; คำสั่งเต็มคือ `select 56`
- เมื่อ M2/Autoplay เปิดอยู่ ระบบจะเล่น playlist ที่ต่อไว้ทั้งหมดก่อน เมื่อรายการสุดท้ายจบจึงกลับไป Related Radio จากเพลงสุดท้าย
- `n`/`b` ในโหมดปกติใช้ Related Radio history เสมอ ไม่ใช้เลื่อน playlist; การเลือกตำแหน่ง playlist ใช้ `c <ลำดับ>` หรือ `select <ลำดับ>`

### Playlist ใน Queue Mode

เมื่อ `q on` อยู่ ทั้ง `u <playlist>` และ `pp <playlist>` จะเพิ่มทั้ง playlist ต่อท้าย FIFO โดยไม่แซงรายการเก่า ข้อความและ Player TTS จะบอก **ชื่อผู้เพิ่ม** กับช่วงลำดับ เช่น `นัท เพิ่มเพลย์ลิสต์ เพลงดังฟังสบาย ลงคิว 10 ถึง 56` ส่วนเพลงเดี่ยวจะบอกผู้เพิ่ม ชื่อเพลง และตำแหน่งคิว เช่น `นัท เพิ่ม เพลงกาฝาก ลงคิวที่ 10` คำสั่ง `ql` จะแสดงผู้เพิ่มและเวลาที่ผ่านมาตั้งแต่รายการนั้นถูกเพิ่มด้วย

`dq <ลำดับ|ชื่อเพลง>` ลบทีละรายการ, `cq` ล้างรายการคิวโดยไม่บังคับหยุดเสียงปัจจุบัน และ `s` คือหยุดพร้อมล้างคิวทั้งหมด

### Cookies สำหรับวิดีโอจำกัดอายุ

Player/Full มี default YouTube cookies จากโปรเจกต์เดิมให้ใช้อัตโนมัติ: instance ใหม่จะ bootstrap เป็น `/app/data/cookies.txt` ถ้ายังไม่มีไฟล์ วันหลังสามารถใช้ `ttuhelper cks` แทนไฟล์ชื่อเดิมด้วย cookie ที่ export เองได้ โดยไฟล์ persistent ที่มีอยู่แล้วจะไม่ถูก default overwrite ดูรายละเอียดใน `YOUTUBE_COOKIES_TH.md`

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
ttuhelper cks <name> [file] ใส่ cookies ให้ Player/Full หนึ่งตัว
ttuhelper cks-check <name> ตรวจรูปแบบ cookies โดยไม่แสดงค่า secret
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

## คิวและ Related Radio

- ในโหมดคิว รายการจะเล่นแบบ FIFO ตามลำดับที่อยู่ในคิว เพลงที่เพิ่มใหม่จะต่อท้ายเสมอ แม้เพิ่มตรงจังหวะเพลงก่อนหน้าจบพอดีก็ตาม
- เมื่อเพลงในคิวเล่นจบ เพลงนั้นจะถูกนำออกจากคิวเพียงรายการเดียว แล้วเล่นรายการเก่าที่รออยู่ถัดไป ไม่มีการล้างหรือกระโดดไปเพลงที่เพิ่งเพิ่มล่าสุด
- `dq <ลำดับ|ชื่อเพลง>` ลบเพียงรายการเดียวที่เลือก; `cq` ล้างรายการคิวแต่ไม่บังคับหยุดเสียงที่กำลังเล่น; `s` หยุด playback และล้างคิวทั้งหมด
- ขณะที่ Queue Mode (`q`) ยังเปิดอยู่ ถ้าคิวหมดหรือใช้ `cq` ล้างคิว เพลงปัจจุบันอาจเล่นต่อจนจบ แต่จะหยุดเมื่อจบและจะไม่หลุดไปเล่น Related Radio เอง
- ในโหมดปกติ `.` คือผลการค้นหาถัดไป และ `,` คือผลการค้นหาก่อนหน้า การเลื่อนผลค้นหาจะเล่นผลที่เลือกทันที
- ใน Queue Mode ผลค้นหาของแต่ละรายการถูกเก็บแยกกัน: `.`/`,` แบบไม่ใส่เลขจะเปลี่ยนรายการค้นหาล่าสุดตามพฤติกรรมเดิม และสามารถใช้ `. 34` หรือ `, 34` เพื่อเลื่อนผลค้นหาของคิว 34 โดยเฉพาะ แม้มีคนอื่นเพิ่มเพลงต่อท้ายแล้วก็ตาม
- ในโหมดปกติ `n`/`b` ไม่ใช้ลำดับผลค้นหาแล้ว แต่ใช้ประวัติ Related Radio: `n` ไปเพลงใกล้เคียงถัดไป และ `b` ย้อนกลับเพลง Related ที่เคยเล่น; ถ้ายังเป็นเพลงแรก `b` จะแจ้งว่าไม่มีเพลงก่อนหน้า
- เมื่อ M2/Autoplay เปิดอยู่ เพลงที่ค้นหาแบบปกติจะต่อด้วย YouTube Mix / YouTube Music Radio; Playlist, Channel และ Favorites ที่เปิดโดยตรงยังรักษาลำดับของรายการนั้น

## ใช้ร่วมกับ SNTalkBot Web Manager

ตั้งแต่ 5.0.1 บอตมี `runtime_status.json` เป็น fallback ใน data directory และใน 5.1.0 เพิ่ม read-only realtime HTTP API ที่ bind loopback พร้อม Bearer token ต่อ instance Web Manager 1.1.0 จะใช้ API ก่อนเพื่อความ realtime สูงสุด แล้ว fallback ไป JSON หาก API ยังไม่พร้อม ใน 5.1.2 ทั้งสองทางแสดงห้องปัจจุบัน, จำนวนคนในห้องและทั้งเซิร์ฟเวอร์แยกกัน, รายชื่อคนในห้อง, Administrator โดยตัดทุก session ที่ใช้ username ของบอต, activity ห้อง/เซิร์ฟเวอร์, เพลง/คิว/ผู้เพิ่มคิว และสถานะ Manager โดยไม่เปลี่ยนคำสั่งหรือ playback core
