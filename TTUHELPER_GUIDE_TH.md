# คู่มือคำสั่ง TTUHelper

TTUHelper ใช้จัดการ SNTalkBot หลาย instance บน Linux ด้วย Docker โดยแต่ละ instance เก็บ config และข้อมูลของตัวเองแยกกัน

| คำสั่ง | ใช้ทำอะไร |
|---|---|
| `ttuhelper new` | สร้าง instance ใหม่ และเลือกโหมด Full / Player / Server Manager |
| `ttuhelper run <name>` | เริ่มบอตจาก config/data ของ instance นั้น |
| `ttuhelper stop <name>` | หยุดและลบ container แต่เก็บ config/data ไว้ |
| `ttuhelper restart <name>` | รีสตาร์ตบอตหนึ่งตัวโดยสร้าง container ใหม่ |
| `ttuhelper delete <name>` | สำรองแล้วลบ instance หลังยืนยันชื่อให้ตรง |
| `ttuhelper logs <name>` | ดูบันทึกการทำงานแบบสด กด `Ctrl+C` เพื่อออก |
| `ttuhelper ls` | ดูรายชื่อ instance ทั้งหมดพร้อมสถานะ running/stopped |
| `ttuhelper ps` | ดู container ที่ TTUHelper จัดการ พร้อมสถานะและ image |
| `ttuhelper start-all` | เริ่มทุก instance ที่มี `config.ini` |
| `ttuhelper stop-all` | หยุด container ทุกตัวที่ TTUHelper จัดการ โดยไม่ลบข้อมูลถาวร |
| `ttuhelper pull` | ดาวน์โหลด Docker image/tag ที่ตั้งไว้ |
| `ttuhelper update` | pull image ใหม่ แล้วอัปเดตเฉพาะ instance ที่กำลังรัน โดยรักษา config/data เดิม |
| `ttuhelper migrate-ttmediabot [path]` | ย้าย TTMediaBot Docker Helper `config.json` v1 ไป SNTalkBot |
| `ttuhelper cks <name> [file]` | แทนที่ `cookies.txt` ของ Player/Full instance จากไฟล์หรือ paste |
| `ttuhelper cks-all [file]` | ใส่ cookies ชุดเดียวให้ Player/Full ทุก instance และข้าม Server Manager |
| `ttuhelper cks-check <name>` | ตรวจ cookies ของ Player/Full โดยไม่แสดงค่า secret |
| `ttuhelper limit <name>` | ตั้งข้อจำกัด CPU/RAM ของ instance มีผลหลัง restart |
| `ttuhelper edit <name>` | เปิด `config.ini` ของ instance ค่าเริ่มต้นใช้ `nano` |
| `ttuhelper path <name>` | แสดงตำแหน่งโฟลเดอร์ config/data ของ instance |
| `ttuhelper doctor` | ตรวจ Docker daemon, image, data root และค่าหลักของ helper |
| `ttuhelper version` | แสดงเวอร์ชัน TTUHelper |
| `ttuhelper help` | แสดงคำอธิบายคำสั่งทั้งหมด |

## ติดตั้ง

เลือกได้ 2 วิธีตามสะดวก ผลลัพธ์เหมือนกัน

### วิธี A: ดาวน์โหลด ZIP จากหน้า Download

```bash
sudo apt-get update
sudo apt-get install -y curl unzip
sudo mkdir -p /opt/ttuhelper
sudo curl -fL https://ttdl.nuttawat.ddnsfree.com/downloads/TTUHelper-latest.zip -o /tmp/TTUHelper.zip
sudo unzip -o /tmp/TTUHelper.zip -d /opt/ttuhelper
cd /opt/ttuhelper
sudo chmod +x install.sh ttuhelper.sh
sudo ./install.sh
sudo ttuhelper doctor
```

### วิธี B: Clone จาก GitHub

```bash
sudo apt-get update
sudo apt-get install -y git
cd /opt
sudo git clone https://github.com/nuttawat-arch/ttuhelper.git
cd /opt/ttuhelper
sudo chmod +x install.sh ttuhelper.sh
sudo ./install.sh
sudo ttuhelper doctor
```

ถ้ามี `/opt/ttuhelper` ที่ clone จาก Git อยู่แล้วและต้องการอัปเดต source ของ helper:

```bash
cd /opt/ttuhelper
sudo git pull --ff-only
sudo ./install.sh
sudo ttuhelper doctor
```

> `ttuhelper update` ใช้อัปเดต **SNTalkBot Docker image/instance** ไม่ใช่ `git pull` ตัว source ของ TTUHelper เอง

สร้างบอต:

```bash
sudo ttuhelper new
sudo ttuhelper run <ชื่อบอต>
```

ดู log:

```bash
sudo ttuhelper logs <ชื่อบอต>
```

อัปเดตบอตที่กำลังรันทั้งหมดโดยรักษาข้อมูลเดิม:

```bash
sudo ttuhelper update
```


## YouTube cookies / วิดีโอจำกัดอายุ

SNTalkBot 5 bootstrap default cookie ให้ Player/Full ที่ `/app/data/cookies.txt` เมื่อ instance ยังไม่มีไฟล์ และ TTUHelper 1.5 ใช้แทนไฟล์ชื่อเดิมด้วยชุดใหม่ได้โดยตรงโดยไม่แตะ Server Manager:

```bash
sudo ttuhelper cks Multipurpose /root/sntalkbot-youtube-cookies.txt
sudo ttuhelper cks-check Multipurpose
sudo ttuhelper restart Multipurpose
```

ดูขั้นตอน export จาก Windows, SCP และข้อควรระวังเรื่อง session credential ใน `YOUTUBE_COOKIES_TH.md`


## Realtime API ภายในสำหรับ Web Manager

TTUHelper 1.5 จองพอร์ต `20000-27999` ที่ว่างให้แต่ละ instance และ bind เฉพาะ `127.0.0.1` เพื่อให้ SNTalkBot Web Manager อ่านสถานะสดโดยไม่ชนกันหลาย instance ห้ามเปิดช่วงพอร์ตนี้ออก Internet; ผู้ใช้เข้าผ่าน Web Manager เท่านั้น

ลบ instance จาก CLI:

```bash
sudo ttuhelper delete <ชื่อบอต>
```

ระบบจะสำรอง config/data ก่อนลบและต้องยืนยันชื่อให้ตรงในโหมด interactive
